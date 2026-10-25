"""Turn policy decisions into the ordered steps_json array and a case status.

Order: phase (FINDING, REMEDIATION, VERIFICATION), then the operation order of
the problem statement's table, then system_id, then resource_id. Because data
flow and restore operations come first in that table, recreation paths are
disabled and blocked before any record is deleted, redacted or anonymized.
"""

from __future__ import annotations

from .policy import Decision

OPERATION_ORDER = [
    ("FINDING", "REPORT_REMAINING_RECORD", "PRESENT"),
    ("FINDING", "REPORT_EXPOSED_PII", "PRESENT"),
    ("FINDING", "REPORT_ACTIVE_DATA_FLOW", "ACTIVE"),
    ("FINDING", "REPORT_RESTORE_RISK", "ACTIVE"),
    ("REMEDIATION", "DISABLE_DATA_FLOW", "DISABLED"),
    ("REMEDIATION", "BLOCK_RESTORE", "BLOCKED"),
    ("REMEDIATION", "DELETE_RECORD", "ABSENT"),
    ("REMEDIATION", "REDACT_RECORD", "REDACTED"),
    ("REMEDIATION", "ANONYMIZE_RECORD", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT"),
    ("VERIFICATION", "VERIFY_RECORD_PRESENT", "PRESENT"),
    ("VERIFICATION", "VERIFY_RECORD_REDACTED", "REDACTED"),
    ("VERIFICATION", "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_DATA_FLOW_DISABLED", "DISABLED"),
    ("VERIFICATION", "VERIFY_RESTORE_BLOCKED", "BLOCKED"),
]
PHASE_OF = {op: phase for phase, op, _ in OPERATION_ORDER}
STATE_OF = {op: state for _, op, state in OPERATION_ORDER}
RANK = {op: i for i, (_, op, _) in enumerate(OPERATION_ORDER)}
KEYS = ("step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id")


def _step(op: str, system_id: str, resource_id: str, evidence_id: str) -> dict:
    return {"phase": PHASE_OF[op], "system_id": system_id, "resource_id": resource_id,
            "operation": op, "state": STATE_OF[op], "evidence_id": evidence_id}


def plan(decisions: list[Decision]) -> tuple[str, list[dict]]:
    """Return (deletion_status, steps) for a deletion-authorized case."""
    incomplete = any(d.violation for d in decisions)
    steps = []
    seen = set()
    for d in decisions:
        st = d.resource
        if not st.citable and not incomplete:
            continue  # a COMPLETE case may only verify what evidence at audit_at proves
        for op in (d.finding, d.remediation, d.verification):
            if not op:
                continue
            # Findings always cite evidence. Remediation and post-remediation checks are future work.
            # A COMPLETE case cites the evidence that proves each verified state.
            if PHASE_OF[op] == "FINDING" or not incomplete:
                evidence = st.evidence_id
            else:
                evidence = ""
            key = (op, st.system_id, st.resource_id)
            if key not in seen:
                seen.add(key)
                steps.append(_step(op, st.system_id, st.resource_id, evidence))
    steps.sort(key=lambda s: (RANK[s["operation"]], s["system_id"], s["resource_id"]))
    numbered = [{"step_no": i, **s} for i, s in enumerate(steps, 1)]
    return ("INCOMPLETE" if incomplete else "COMPLETE"), [{k: s[k] for k in KEYS} for s in numbered]
