"""Evaluation workflow.

Runs the full pipeline on the 32 public sample requests and on our custom cases,
scores the results against the expected answers, prints the metrics, and (with
--write-report) writes code/evaluation/evaluation_report.md.

Usage (from the repository root):
  python code/evaluation/main.py --offline                 # score from cached model answers
  python code/evaluation/main.py --offline --verbose       # also list every failing step
  python code/evaluation/main.py --offline --write-report  # regenerate evaluation_report.md
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from collections import Counter
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR.parent))
sys.path.insert(0, str(EVAL_DIR))

from audit.config import DATASET_DIR, load_settings  # noqa: E402
from audit.index import build_index  # noqa: E402
from audit.llm.gateway import Gateway  # noqa: E402
from audit.pipeline import run  # noqa: E402
from custom_cases import CASES  # noqa: E402
from metrics import score_case, summarize  # noqa: E402
from report import write_report  # noqa: E402


def load_expected(path: Path) -> dict[str, tuple[str, list]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in csv.DictReader(fh)}


def _score(expected: dict, predicted: dict) -> dict:
    scores, pairs = [], []
    for cid, (exp_status, exp_steps) in sorted(expected.items()):
        pred_status, pred_steps = predicted[cid]
        scores.append(score_case(cid, exp_status, exp_steps, pred_status, pred_steps))
        pairs.append((exp_steps, pred_steps))
    summary = summarize(scores, pairs)
    summary["scores"] = scores
    summary["failures"] = [s for s in scores if not (s.exact_sequence and s.expected_status == s.predicted_status)]
    return summary


def _print(title: str, summary: dict, verbose: bool) -> None:
    print(f"== {title}: {summary['cases']} cases")
    print(f"status accuracy : {summary['status_accuracy']:.1%}")
    print(f"step P/R/F1     : {summary['step_precision']:.1%} / {summary['step_recall']:.1%} / {summary['step_f1']:.1%}")
    print(f"exact step set  : {summary['exact_step_set']:.1%}")
    print(f"exact sequence  : {summary['exact_sequence']:.1%}   mean LCS ratio: {summary['mean_lcs_ratio']:.1%}")
    print("field accuracy  : " + ", ".join(f"{k}={v:.1%}" for k, v in summary["field_accuracy"].items()))
    for s in summary["failures"]:
        print(f"  FAIL {s.case_id}: status {s.expected_status}->{s.predicted_status}, missing {len(s.missing)}, "
              f"extra {len(s.extra)}, lcs {s.lcs_ratio:.0%}")
        if verbose:
            for m in s.missing:
                print("     - missing", m)
            for x in s.extra:
                print("     + extra  ", x)


def evaluate(settings, verbose: bool = False, write: bool = False) -> dict:
    gateway = Gateway(settings)
    index = build_index(settings, gateway)

    sample_expected = load_expected(DATASET_DIR / "sample_output.csv")
    sample_run = run(settings, DATASET_DIR / "sample_deletion_requests.csv", index=index, gateway=gateway)
    samples = _score(sample_expected, {cid: (st, steps) for cid, st, steps in sample_run.rows})
    intent_sources = Counter(s["intent"].source for s in sample_run.states.values())

    custom_run = run(settings, None, extra_requests=[c.request for c in CASES],
                     exclude_from_pool=frozenset(c.twin_of for c in CASES if c.twin_of), index=index,
                     gateway=gateway)
    custom_expected = {c.request.case_id: (c.expected_status, c.expected_steps) for c in CASES}
    custom = _score(custom_expected, {cid: (st, steps) for cid, st, steps in custom_run.rows})
    custom["predicted"] = {cid: (st, steps) for cid, st, steps in custom_run.rows}

    _print("public samples", samples, verbose)
    _print("custom cases", custom, verbose)
    if write:
        known = set(index.by_resource) | set(index.activity_by_resource)
        path = write_report(samples, custom, CASES, settings, gateway.usage.as_dict(), intent_sources, known)
        print(f"wrote {path}")
    return {"samples": samples, "custom": custom}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the audit agent on the public samples and custom cases")
    parser.add_argument("--offline", action="store_true", help="use cached model answers only")
    parser.add_argument("--verbose", action="store_true", help="list every missing and extra step")
    parser.add_argument("--write-report", action="store_true", help="regenerate evaluation_report.md")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    evaluate(load_settings(offline=args.offline), verbose=args.verbose, write=args.write_report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
