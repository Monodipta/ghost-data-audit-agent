"""Ghost Data audit agent - command line entry point.

Usage:
  python code/main.py index [--offline]     Stage A: parse all evidence, print a summary
  python code/main.py run [--offline] [--requests PATH] [--out PATH] [--trace]
                                            Audit every request and write output.csv
  python code/evaluation/main.py [--offline] Score against the public samples and custom cases
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit.config import load_settings  # noqa: E402
from audit.index import build_index  # noqa: E402
from audit.llm.gateway import Gateway  # noqa: E402


def cmd_index(args: argparse.Namespace) -> int:
    settings = load_settings(offline=args.offline)
    gateway = Gateway(settings)
    index = build_index(settings, gateway)
    print(f"evidence files : {len(index.files)}")
    print(f"observations   : {len(index.observations)}")
    print(f"coverages      : {len(index.coverages)}")
    print(f"activity events: {len(index.activity)}")
    print(f"resources      : {len(index.by_resource)}")
    by_file = Counter(o.evidence_id for o in index.observations)
    empty = sorted(f for f in index.files if not by_file.get(f) and
                   not any(c.evidence_id == f for c in index.coverages))
    print(f"files with no facts: {', '.join(empty) or 'none'}")
    print(f"warnings       : {len(index.warnings)}")
    for model, usage in gateway.usage.as_dict().items():
        print(f"model {model}: {usage['calls']} calls, {usage['cached_calls']} cached, "
              f"{usage['input_tokens']} in / {usage['output_tokens']} out tokens")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from audit.output import case_sort_key
    from audit.pipeline import run

    settings = load_settings(offline=args.offline)
    result = run(settings, Path(args.requests), Path(args.out), trace=args.trace)
    statuses = Counter(status for _, status, _ in result.rows)
    invalid = [cid for cid, s in result.states.items() if s.get("errors")]
    print(f"wrote {len(result.rows)} rows to {args.out}")
    print("status counts: " + ", ".join(f"{k}={v}" for k, v in sorted(statuses.items())))
    print(f"steps: {sum(len(steps) for _, _, steps in result.rows)}; invalid rows: {len(invalid)}"
          + (f" ({', '.join(sorted(invalid, key=case_sort_key)[:10])})" if invalid else ""))
    for model, usage in result.gateway.usage.as_dict().items():
        print(f"model {model}: {usage['calls']} calls, {usage['cached_calls']} cached, "
              f"{usage['input_tokens']} in / {usage['output_tokens']} out tokens")
    if not args.no_usage_report:
        from audit.usage_report import write_usage_report

        path = write_usage_report(result.gateway.usage.as_dict(), result.gateway.usage.tasks, len(result.rows),
                                  settings.offline, Path(args.out))
        print(f"wrote {path}")
    return 1 if invalid else 0


def main(argv: list[str] | None = None) -> int:
    from audit.config import DATASET_DIR, OUTPUT_PATH

    parser = argparse.ArgumentParser(description="Ghost Data deletion audit agent")
    sub = parser.add_subparsers(dest="command", required=True)
    p_index = sub.add_parser("index", help="Stage A: parse and index all evidence")
    p_index.add_argument("--offline", action="store_true", help="use cached model answers only")
    p_index.set_defaults(func=cmd_index)
    p_run = sub.add_parser("run", help="audit every request and write output.csv")
    p_run.add_argument("--offline", action="store_true", help="use cached model answers only")
    p_run.add_argument("--requests", default=str(DATASET_DIR / "deletion_requests.csv"))
    p_run.add_argument("--out", default=str(OUTPUT_PATH))
    p_run.add_argument("--trace", action="store_true", help="write one JSON trace per case to code/traces/")
    p_run.add_argument("--no-usage-report", action="store_true", help="do not rewrite evaluation/usage_report.md")
    p_run.set_defaults(func=cmd_run)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("audit").setLevel(logging.INFO)  # per-document progress
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
