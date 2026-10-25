"""Stage B unit tests: identity, intent rules, state + citation, policy, planner, validator, linking.

Run: python -m unittest discover -s code/tests
All inputs are synthetic; no dataset files or ids are used.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit.activity import ActivityEvent  # noqa: E402
from audit.identity import IdentityResolver, email_sha256  # noqa: E402
from audit.index import EvidenceIndex  # noqa: E402
from audit.intent import rule_label  # noqa: E402
from audit.linking import link_all  # noqa: E402
from audit.models import Coverage, EvidenceFile, Observation, Request, ResourceState  # noqa: E402
from audit.planner import plan  # noqa: E402
from audit.policy import Policy  # noqa: E402
from audit.state import resolve_state  # noqa: E402
from audit.validate import validate_row  # noqa: E402

RULES = [
    {"rule_id": "r1", "data_category": "USER_PROFILE", "condition": "Always", "required_action": "DELETE"},
    {"rule_id": "r2", "data_category": "SEARCH_INDEX_ENTRY", "condition": "Always", "required_action": "DELETE"},
    {"rule_id": "r3", "data_category": "ANALYTICS_PROFILE", "condition": "x", "required_action": "ANONYMIZE"},
    {"rule_id": "r4", "data_category": "SUPPORT_MESSAGE", "condition": "x", "required_action": "REDACT"},
    {"rule_id": "r5", "data_category": "SECURITY_AUDIT_LOG", "condition": "x", "required_action": "RETAIN"},
    {"rule_id": "r6", "data_category": "BACKUP_ARCHIVE", "condition": "x", "required_action": "RETAIN"},
    {"rule_id": "r7", "data_category": "ACCOUNT_TOMBSTONE", "condition": "x", "required_action": "REDACT"},
]
AUDIT = "2026-05-01T00:00:00Z"


def _index(observations, coverages=(), files=None, activity=()):
    files = files or {}
    for o in observations:
        files.setdefault(o.evidence_id, EvidenceFile(o.evidence_id, "p", "o", o.observed_at))
    for c in coverages:
        files.setdefault(c.evidence_id, EvidenceFile(c.evidence_id, "p", "o", c.observed_at))
    idx = EvidenceIndex(files, list(observations), list(coverages), list(activity), [])
    idx.build_maps()
    return idx


def _st(category, exists=True, exposed=None, active=None, via="explicit", system="s", rid="r_1", ev="f1"):
    return ResourceState(system, rid, category, exists, exposed, active, ev, "2026-04-01T00:00:00Z", via)


class IdentityTests(unittest.TestCase):
    def setUp(self):
        identities = [{"user_id": "user_1", "name": "Ana Lima", "email": "c@x.io", "phone": "+1 555 0101",
                       "email_hash": email_sha256("c@x.io"), "updated_at": "t"}]
        audit = [
            {"audit_id": "a1", "user_id": "user_1", "event_time": "2025-01-01T00:00:00Z", "field_name": "email",
             "old_value": "a@x.io", "new_value": "b@x.io"},
            {"audit_id": "a2", "user_id": "user_1", "event_time": "2025-06-01T00:00:00Z", "field_name": "email",
             "old_value": "b@x.io", "new_value": "c@x.io"},
        ]
        self.resolver = IdentityResolver(identities, audit)

    def test_oldest_email_in_chain_resolves_case_insensitively(self):
        ident = self.resolver.resolve("A@X.IO", AUDIT)
        self.assertEqual(ident.user_id, "user_1")
        self.assertEqual(ident.emails, {"a@x.io", "b@x.io", "c@x.io"})

    def test_hashes_of_every_email(self):
        ident = self.resolver.resolve("c@x.io", AUDIT)
        self.assertIn(("hash", email_sha256("a@x.io")), ident.strong_ids)
        self.assertNotIn("name", {k for k, _ in ident.strong_ids})  # names never link alone


class IntentRuleTests(unittest.TestCase):
    def test_negations_win(self):
        for text in ("I am not asking for deletion, just stop the emails.",
                     "Please don't delete anything, I need a copy.",
                     "Remove me from marketing lists only.",
                     "Fix my name without removing any of my records."):
            self.assertEqual(rule_label(text), "NOT_DELETION", text)

    def test_deletion_paraphrases_and_languages(self):
        for text in ("I'm deleting my account.", "Confirm the profile is gone.", "Please erase my data.",
                     "Solicito la eliminación de mi cuenta.", "アカウントを削除してください。",
                     "You may keep backups if required, but close my account."):
            self.assertEqual(rule_label(text), "DELETION", text)


class StateTests(unittest.TestCase):
    def test_latest_explicit_and_replica_ghost(self):
        obs = [
            Observation("f1", "2026-03-01T00:00:00Z", "account_service", "account_1", "USER_PROFILE", True),
            Observation("f2", "2026-04-01T00:00:00Z", "account_service", "account_1", "USER_PROFILE", False,
                        instance="primary"),
            Observation("f2", "2026-04-01T00:00:00Z", "account_service", "account_1", "USER_PROFILE", True,
                        instance="replica"),
        ]
        st = resolve_state(_index(obs), "account_1", AUDIT)
        self.assertEqual((st.exists, st.evidence_id, st.via), (True, "f2", "explicit"))

    def test_file_captured_after_audit_is_not_cited(self):
        obs = [Observation("f1", "2026-03-01T00:00:00Z", "s", "account_1", "USER_PROFILE", True),
               Observation("late", "2026-04-30T00:00:00Z", "s", "account_1", "USER_PROFILE", False)]
        files = {"late": EvidenceFile("late", "p", "o", "2026-05-02T00:00:00Z")}
        st = resolve_state(_index(obs, files=files), "account_1", AUDIT)
        self.assertEqual((st.exists, st.evidence_id), (True, "f1"))

    def test_coverage_proves_absence_and_empty_snapshots_do_not(self):
        act = [ActivityEvent("a1", "2026-02-01T00:00:00Z", "DELETE_RECORD", "w", "account_service", "account_9",
                             "SUCCESS", "", "USER_PROFILE", "account_service")]
        covs = [Coverage("good", "2026-03-01T00:00:00Z", "account_service", "USER_PROFILE", "primary",
                         frozenset({"account_2"}), 5),
                Coverage("empty", "2026-04-01T00:00:00Z", "account_service", "USER_PROFILE", "primary",
                         frozenset(), 0)]
        st = resolve_state(_index([], covs, activity=act), "account_9", AUDIT)
        self.assertEqual((st.exists, st.evidence_id, st.via), (False, "good", "coverage"))


class PolicyAndPlanTests(unittest.TestCase):
    policy = Policy(RULES)

    def test_policy_table(self):
        p = self.policy
        self.assertEqual(p.decide(_st("SEARCH_INDEX_ENTRY"), AUDIT).finding, "REPORT_REMAINING_RECORD")
        self.assertEqual(p.decide(_st("SEARCH_INDEX_ENTRY", exists=False), AUDIT).verification, "VERIFY_RECORD_ABSENT")
        self.assertEqual(p.decide(_st("ANALYTICS_PROFILE", exposed=True), AUDIT).remediation, "ANONYMIZE_RECORD")
        self.assertFalse(p.decide(_st("SUPPORT_MESSAGE", exposed=False), AUDIT).violation)
        self.assertEqual(p.decide(_st("SECURITY_AUDIT_LOG"), AUDIT).verification, "VERIFY_RECORD_PRESENT")
        self.assertEqual(p.decide(_st("BACKUP_ARCHIVE", active=True), AUDIT).finding, "REPORT_RESTORE_RISK")
        self.assertEqual(p.decide(_st("DATA_FLOW", active=True), AUDIT).remediation, "DISABLE_DATA_FLOW")
        self.assertEqual(p.decide(_st("ACCOUNT_TOMBSTONE", exposed=True), AUDIT).remediation, "REDACT_RECORD")

    def test_late_known_state_never_produces_a_finding(self):
        self.assertIsNone(self.policy.decide(_st("SEARCH_INDEX_ENTRY", via="known_late"), AUDIT))
        d = self.policy.decide(_st("SECURITY_AUDIT_LOG", via="known_late"), AUDIT)
        self.assertEqual((d.violation, d.verification), (False, "VERIFY_RECORD_PRESENT"))

    def test_plan_order_and_evidence(self):
        decisions = [self.policy.decide(s, AUDIT) for s in (
            _st("SEARCH_INDEX_ENTRY", system="search_service", rid="search_1", ev="f1"),
            _st("DATA_FLOW", active=True, system="integration_service", rid="data_flow_1", ev="f2"),
            _st("USER_PROFILE", exists=False, system="account_service", rid="account_1", ev="f3"),
        )]
        status, steps = plan(decisions)
        self.assertEqual(status, "INCOMPLETE")
        self.assertEqual([s["operation"] for s in steps], [
            "REPORT_REMAINING_RECORD", "REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW", "DELETE_RECORD",
            "VERIFY_RECORD_ABSENT", "VERIFY_RECORD_ABSENT", "VERIFY_DATA_FLOW_DISABLED"])
        self.assertEqual([s["step_no"] for s in steps], list(range(1, 8)))
        self.assertTrue(all(s["evidence_id"] for s in steps if s["phase"] == "FINDING"))
        self.assertTrue(all(s["evidence_id"] == "" for s in steps if s["phase"] != "FINDING"))
        self.assertEqual(validate_row(status, steps, AUDIT, {}), [])

    def test_complete_cites_evidence(self):
        status, steps = plan([self.policy.decide(_st("USER_PROFILE", exists=False, ev="f9"), AUDIT)])
        self.assertEqual((status, steps[0]["evidence_id"]), ("COMPLETE", "f9"))

    def test_validator_rejects_bad_rows(self):
        bad = [{"step_no": 2, "phase": "REMEDIATION", "system_id": "s", "resource_id": "r",
                "operation": "DELETE_RECORD", "state": "ABSENT", "evidence_id": "f1"}]
        errors = validate_row("COMPLETE", bad, AUDIT, {"f1": "2026-06-01T00:00:00Z"})
        self.assertTrue(any("step_no" in e for e in errors))
        self.assertTrue(any("after audit_at" in e for e in errors))
        self.assertTrue(any("only verification" in e for e in errors))
        self.assertTrue(validate_row("NOT_APPLICABLE", bad, AUDIT, {}))


class LinkingTests(unittest.TestCase):
    def test_identifier_link_and_global_workflow_assignment(self):
        identities = [{"user_id": "user_1", "name": "A", "email": "a@x.io", "phone": "", "email_hash": "",
                       "updated_at": "t"},
                      {"user_id": "user_2", "name": "B", "email": "b@x.io", "phone": "", "email_hash": "",
                       "updated_at": "t"}]
        resolver = IdentityResolver(identities, [])
        reqs = [Request("c1", "a@x.io", "2026-04-01T00:00:00Z", "COMPLETE", "2026-04-02T12:00:00Z", AUDIT, "t"),
                Request("c2", "b@x.io", "2026-04-01T00:00:00Z", "COMPLETE", "2026-04-02T15:00:00Z", AUDIT, "t")]
        obs = [Observation("f1", "2026-04-10T00:00:00Z", "search_service", "search_1", "SEARCH_INDEX_ENTRY", True,
                           link_ids=frozenset({("email", "a@x.io")}))]
        act = [ActivityEvent("e1", "2026-04-02T11:55:00Z", "DELETE_RECORD", "deletion_worker", "account_service",
                             "account_1", "SUCCESS", "", "USER_PROFILE", "account_service"),
               ActivityEvent("e2", "2026-04-02T14:58:00Z", "DELETE_RECORD", "deletion_worker", "account_service",
                             "account_2", "SUCCESS", "", "USER_PROFILE", "account_service")]
        idx = _index(obs, activity=act)
        idents = {r.case_id: resolver.resolve(r.email, r.audit_at) for r in reqs}
        links = link_all(reqs, idents, idx, resolver)
        self.assertEqual(set(links["c1"].resources), {"search_1", "account_1"})
        self.assertEqual(set(links["c2"].resources), {"account_2"})


if __name__ == "__main__":
    unittest.main()
