"""Check one output row against the output contract before it is written."""

from __future__ import annotations

from .planner import KEYS, PHASE_OF, RANK, STATE_OF

STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}
PHASES = ["FINDING", "REMEDIATION", "VERIFICATION"]


def validate_row(status: str, steps: list[dict], audit_at: str, evidence_times: dict[str, str]) -> list[str]:
    """Return a list of problems (empty when the row is valid)."""
    errors = []
    if status not in STATUSES:
        errors.append(f"unknown status {status!r}")
    if status == "NOT_APPLICABLE" and steps:
        errors.append("NOT_APPLICABLE must have an empty steps array")
    for i, s in enumerate(steps, 1):
        if tuple(s.keys()) != KEYS:
            errors.append(f"step {i}: fields must be exactly {KEYS}")
            continue
        if s["step_no"] != i:
            errors.append(f"step {i}: step_no is {s['step_no']}")
        op = s["operation"]
        if op not in PHASE_OF:
            errors.append(f"step {i}: unknown operation {op}")
            continue
        if s["phase"] != PHASE_OF[op] or s["state"] != STATE_OF[op]:
            errors.append(f"step {i}: {op} needs phase {PHASE_OF[op]} and state {STATE_OF[op]}")
        ev = s["evidence_id"]
        must_cite = s["phase"] == "FINDING" or status == "COMPLETE"
        if must_cite and not ev:
            errors.append(f"step {i}: {op} must cite evidence")
        if not must_cite and ev:
            errors.append(f"step {i}: future {op} must use an empty evidence_id")
        if ev and ev in evidence_times and evidence_times[ev] > audit_at:
            errors.append(f"step {i}: cites {ev} captured after audit_at")
    keys = [(RANK.get(s["operation"], 99), s["system_id"], s["resource_id"]) for s in steps]
    if keys != sorted(keys):
        errors.append("steps are not in the required order")
    if status == "COMPLETE" and any(s["phase"] != "VERIFICATION" for s in steps):
        errors.append("COMPLETE may contain only verification steps")
    if status == "INCOMPLETE" and not any(s["phase"] == "FINDING" for s in steps):
        errors.append("INCOMPLETE needs at least one finding")
    return errors
