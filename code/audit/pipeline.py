"""End-to-end run: Stage A index -> intent -> identity -> global linking -> case graph -> output."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .config import DATASET_DIR, TRACE_DIR, Settings
from .graph import CaseContext, build_graph
from .identity import IdentityResolver
from .index import EvidenceIndex, build_index
from .intent import classify_all
from .linking import link_all
from .llm.gateway import Gateway
from .loaders import read_csv
from .models import Request
from .output import write_output
from .policy import Policy

log = logging.getLogger(__name__)
REQUEST_FILES = ("deletion_requests.csv", "sample_deletion_requests.csv")


def load_requests(path: Path) -> list[Request]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        import csv

        return [Request(**{k: (v or "").strip() if k != "request_text" else v for k, v in row.items()})
                for row in csv.DictReader(fh)]


@dataclass
class RunResult:
    rows: list[tuple[str, str, list[dict]]]
    states: dict[str, dict]
    index: EvidenceIndex
    gateway: Gateway


def run(settings: Settings, requests_path: Path | None, out_path: Path | None = None, trace: bool = False,
        extra_requests: list[Request] | None = None, exclude_from_pool: frozenset = frozenset(),
        index: EvidenceIndex | None = None, gateway: Gateway | None = None) -> RunResult:
    """Audit the requests in requests_path (plus extra_requests).

    exclude_from_pool removes known requests from global linking; the evaluator uses it when a custom
    case stands in for an existing request, so the two do not compete for the same resources.
    """
    gateway = gateway or Gateway(settings)
    index = index or build_index(settings, gateway)
    targets = (load_requests(requests_path) if requests_path else []) + list(extra_requests or [])

    # Every known request takes part in global linking, so nearby cases compete fairly for resources.
    pool = {r.case_id: r for f in REQUEST_FILES for r in load_requests(DATASET_DIR / f)
            if r.case_id not in exclude_from_pool}
    pool.update({r.case_id: r for r in targets})

    intents = classify_all([r.request_text for r in targets], gateway, settings.intent_model)
    resolver = IdentityResolver(read_csv("user_identities.csv"), read_csv("user_audit_log.csv"))
    identities = {cid: resolver.resolve(r.email, r.audit_at) for cid, r in pool.items()}
    unresolved = [cid for cid in pool if identities[cid].user_id is None and cid in {t.case_id for t in targets}]
    if unresolved:
        log.warning("%d request emails match no known user: %s", len(unresolved), ", ".join(unresolved[:10]))
    links = link_all(list(pool.values()), identities, index, resolver)

    ctx = CaseContext(index, intents, identities, links, Policy(read_csv("deletion_rules.csv")))
    graph = build_graph(ctx)
    outputs = graph.batch([{"request": r} for r in targets], config={"max_concurrency": 8})

    rows, states = [], {}
    for req, out in zip(targets, outputs):
        if out.get("errors"):
            log.error("%s: invalid row: %s", req.case_id, "; ".join(out["errors"]))
        rows.append((req.case_id, out["status"], out["steps"]))
        states[req.case_id] = out
    if out_path:
        write_output(rows, out_path)
    if trace:
        _write_traces(states)
    return RunResult(rows, states, index, gateway)


def _write_traces(states: dict[str, dict]) -> None:
    """One JSON trace per case: identifiers, links, states and decisions behind every step."""
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    for case_id, s in states.items():
        ident = s.get("identity")
        doc = {
            "case_id": case_id,
            "intent": vars(s["intent"]) if s.get("intent") else None,
            "identity": {"user_id": ident.user_id, "emails": sorted(ident.emails), "phones": sorted(ident.phones),
                         "hashes": len(ident.hashes)} if ident else None,
            "linked": s.get("linked"),
            "states": [vars(st) | {"details": list(st.details)} for st in s.get("states", [])],
            "decisions": [{"resource": d.resource.resource_id, "violation": d.violation, "rule": d.rule_id,
                           "ops": [d.finding, d.remediation, d.verification]} for d in s.get("decisions", [])],
            "status": s.get("status"),
            "errors": s.get("errors"),
        }
        (TRACE_DIR / f"{case_id}.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
