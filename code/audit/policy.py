"""Apply deletion_rules.csv to a resource's state.

The rules file maps each data category to a required action. A record either
already meets it (verification only) or violates it (finding, remediation and
verification). Data flows and backups are handled as recreation paths: an
active flow must be disabled, a restorable backup must be blocked (the backup
itself is retained by rule).
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import ResourceState

# (finding, remediation, verification) per required action
DELETE = ("REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT")
REDACT = ("REPORT_EXPOSED_PII", "REDACT_RECORD", "VERIFY_RECORD_REDACTED")
ANONYMIZE = ("REPORT_EXPOSED_PII", "ANONYMIZE_RECORD", "VERIFY_RECORD_ANONYMIZED")
FLOW = ("REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW", "VERIFY_DATA_FLOW_DISABLED")
RESTORE = ("REPORT_RESTORE_RISK", "BLOCK_RESTORE", "VERIFY_RESTORE_BLOCKED")
TRIPLES = {"DELETE": DELETE, "REDACT": REDACT, "ANONYMIZE": ANONYMIZE}


@dataclass(frozen=True)
class Decision:
    resource: ResourceState
    violation: bool
    finding: str | None
    remediation: str | None
    verification: str | None
    rule_id: str | None


class Policy:
    def __init__(self, rules: list[dict]):
        self.action_by_category: dict[str, tuple[str, str]] = {}
        for r in rules:
            self.action_by_category.setdefault(r["data_category"].strip(), (r["required_action"].strip(), r["rule_id"]))

    def decide(self, st: ResourceState, audit_at: str) -> Decision | None:
        """Return the decision for one resource, or None when no step applies."""
        if not st.citable:
            # Known only from an export captured after audit_at. No violation can be proven with it, but a
            # record already in its required state still gets a future check that must keep passing.
            decision = self._decide(st, audit_at)
            if decision is None or decision.violation:
                return None
            return decision
        return self._decide(st, audit_at)

    def _decide(self, st: ResourceState, audit_at: str) -> Decision | None:
        cat = st.category
        if cat == "DATA_FLOW":
            if st.exists is False or st.active is None:
                return None
            return Decision(st, st.active, *(FLOW if st.active else (None, None, FLOW[2])), None)
        if cat is None or cat not in self.action_by_category:
            return None
        action, rule_id = self.action_by_category[cat]

        if cat == "BACKUP_ARCHIVE":  # RETAIN the archive; the restore path must be blocked
            if st.exists is False or st.active is None:
                return None
            return Decision(st, st.active, *(RESTORE if st.active else (None, None, RESTORE[2])), rule_id)

        if action == "RETAIN":
            if not st.exists:
                return None
            if self._retention_expired(st, audit_at):
                return Decision(st, True, *DELETE, rule_id)
            return Decision(st, False, None, None, "VERIFY_RECORD_PRESENT", rule_id)

        if action == "DELETE":
            if st.exists is None:
                return None
            return Decision(st, bool(st.exists), *(DELETE if st.exists else (None, None, DELETE[2])), rule_id)

        if action in ("REDACT", "ANONYMIZE"):
            triple = TRIPLES[action]
            if st.exists is None:
                return None
            if st.exists is False:
                if cat == "ACCOUNT_TOMBSTONE":
                    return None  # the tombstone should exist; nothing to verify as redacted
                return Decision(st, False, None, None, DELETE[2], rule_id)
            # A record whose identifiers are not shown to be removed is treated as still exposed.
            if st.exposed is False:
                return Decision(st, False, None, None, triple[2], rule_id)
            return Decision(st, True, *triple, rule_id)
        return None

    @staticmethod
    def _retention_expired(st: ResourceState, audit_at: str) -> bool:
        for key, value in st.details:
            if key in ("retention_until", "retained_until") and value and value < audit_at:
                return True
        return False
