"""Stage A unit tests: normalization, record mapping, every log style, SQL coverage.

Run: python -m unittest discover -s code/tests
All inputs are synthetic; no dataset files or ids are used.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CODE_DIR))

from audit import normalize as nz  # noqa: E402
from audit.evidence import json_records, logs, sql, text  # noqa: E402
from audit.evidence.records import from_record, from_result_row  # noqa: E402
from audit.models import EvidenceFile  # noqa: E402

ENTRY = EvidenceFile("file_x", "evidence/x", "test", "2026-01-02T03:04:05Z")


class NormalizeTests(unittest.TestCase):
    def test_email_is_lowercased_and_trimmed(self):
        self.assertEqual(nz.email("  Person.One@Example.COM "), "person.one@example.com")

    def test_null_like_values_are_missing(self):
        for value in (None, "", "null", "NULL", '"null"', "no direct identifier"):
            self.assertIsNone(nz.clean(value))

    def test_phone_keeps_digits_only(self):
        self.assertEqual(nz.phone("+44 20 7946-0000"), "+442079460000")

    def test_reference_classifies_mixed_fields(self):
        self.assertEqual(nz.reference("user_77"), ("user", "user_77"))
        self.assertEqual(nz.reference("A@B.io"), ("email", "a@b.io"))
        self.assertEqual(nz.reference("ab" * 32), ("hash", "ab" * 32))

    def test_timestamp_normalization(self):
        self.assertEqual(nz.ts("2026-05-06T07:08:09+00:00"), "2026-05-06T07:08:09Z")


class RecordMappingTests(unittest.TestCase):
    def test_raw_record_with_identifiers_is_exposed(self):
        obs = from_record("f", "2026-01-01T00:00:00Z", "analytics_platform", "customer_analytics_reports",
                          {"resource_id": "analytics_1", "user_id": "user_9", "email": "P@X.io", "phone": None})
        self.assertEqual(obs.category, "ANALYTICS_PROFILE")
        self.assertTrue(obs.exists)
        self.assertTrue(obs.exposed)
        self.assertIn(("email", "p@x.io"), obs.link_ids)

    def test_anonymized_record_is_not_exposed(self):
        obs = from_record("f", "t", "analytics_platform", "customer_analytics_reports",
                          {"resource_id": "analytics_2", "user_id": None, "email": None})
        self.assertFalse(obs.exposed)

    def test_redacted_support_message(self):
        obs = from_record("f", "t", "support_platform", "support_conversations",
                          {"resource_id": "support_3", "subject_reference": "user_4", "message_text": "[REDACTED]"})
        self.assertEqual(obs.category, "SUPPORT_MESSAGE")
        self.assertFalse(obs.exposed)

    def test_attachment_detected_from_fields(self):
        obs = from_record("f", "t", "support_platform", "support_conversations",
                          {"resource_id": "support_5", "ticket_id": "T1", "file_name": "a.pdf", "uploaded_by": "q@x.io"})
        self.assertEqual(obs.category, "SUPPORT_ATTACHMENT")

    def test_backup_restore_flag(self):
        obs = from_record("f", "t", "backup_service", "backup_catalog",
                          {"resource_id": "backup_6", "subject_reference": "user_1", "restore_allowed": "1"})
        self.assertTrue(obs.active)

    def test_404_lookup_is_absent(self):
        obs = from_record("f", "t", "account_service", "profile_lookups",
                          {"resource_id": "account_7", "status_code": 404, "profile": None})
        self.assertFalse(obs.exists)

    def test_result_row_states(self):
        self.assertFalse(from_result_row("f", "t", "account_service", "account_1", "USER_PROFILE",
                                         "NOT_FOUND", "a@b.io").exists)
        flow = from_result_row("f", "t", "integration_service", "data_flow_1", "DATA_FLOW", "ACTIVE", "user_2")
        self.assertTrue(flow.active)
        self.assertIsNone(from_result_row("f", "t", "x", "account_1", "USER_PROFILE", "WEIRD", None))


class LogStyleTests(unittest.TestCase):
    """One started + one completed line per style must yield one linked observation."""

    STYLES = {
        "logfmt": [
            '2026-01-01T00:00:00Z level=DEBUG service=account_service trace_id=t1 event=profile_lookup_started '
            'lookup_key="p@x.io"',
            "2026-01-01T00:00:01Z level=INFO service=account_service trace_id=t1 resource_id=account_1 "
            "event=profile_lookup_completed rows=0 http_status=404",
        ],
        "pipe": [
            '2026-01-01T00:00:00Z | DEBUG | account_service | t1 | profile_lookup_started | lookup_key="p@x.io"',
            '2026-01-01T00:00:01Z | INFO | account_service | t1 | profile_lookup_completed | '
            'resource_id="account_1" rows="0" http_status="404"',
        ],
        "bracket": [
            '2026-01-01T00:00:00Z [DEBUG] [account_service] [t1] profile_lookup_started: lookup_key="p@x.io"',
            '2026-01-01T00:00:01Z [INFO] [account_service] [t1] profile_lookup_completed: resource_id="account_1" '
            'rows="0" http_status="404"',
        ],
        "cloud": [
            '2026-01-01T00:00:00Z requestId=t1 level=DEBUG function=profile_service message="event=\\"profile_lookup_'
            'started\\" lookup_key=\\"p@x.io\\""',
            '2026-01-01T00:00:01Z requestId=t1 level=INFO function=profile_service message="resource_id=\\"account_1\\"'
            ' event=\\"profile_lookup_completed\\" rows=\\"0\\" http_status=\\"404\\""',
        ],
        "syslog": [
            '2026-01-01T00:00:00Z <14>1 node-1 account_service t1 - - level=DEBUG event="profile_lookup_started" '
            'lookup_key="p@x.io"',
            '2026-01-01T00:00:01Z <14>1 node-1 account_service t1 - - level=INFO resource_id="account_1" '
            'event="profile_lookup_completed" rows="0" http_status="404"',
        ],
        "json": [
            '2026-01-01T00:00:00Z {"service":"account_service","trace_id":"t1","event":"profile_lookup_started",'
            '"lookup_key":"p@x.io"}',
            '2026-01-01T00:00:01Z {"service":"account_service","trace_id":"t1","resource_id":"account_1",'
            '"event":"profile_lookup_completed","rows":"0","http_status":"404"}',
        ],
    }

    def test_every_style(self):
        for style, lines in self.STYLES.items():
            with self.subTest(style=style):
                result = logs.parse(ENTRY, "\n".join(lines))
                self.assertEqual(len(result.observations), 1, style)
                obs = result.observations[0]
                self.assertEqual(obs.resource_id, "account_1")
                self.assertEqual(obs.system_id, "account_service")
                self.assertFalse(obs.exists)
                self.assertIn(("email", "p@x.io"), obs.link_ids)

    def test_record_lookup_line(self):
        line = ('2026-01-01T00:00:00Z INFO service=x event=record_lookup system="search_service" '
                'resource_id="search_1" record_type="SEARCH_INDEX_ENTRY" result="FOUND" subject_reference="p@x.io"')
        obs = logs.parse(ENTRY, line).observations[0]
        self.assertTrue(obs.exists)
        self.assertEqual(obs.category, "SEARCH_INDEX_ENTRY")

    def test_noise_and_retries_are_not_absence(self):
        lines = [
            '2026-01-01T00:00:00Z [WARN] [account_service] [t1] dependency_retry: reason="read_timeout"',
            '2026-01-01T00:00:01Z [DEBUG] [account_service] [t1] cache_lookup: result="miss"',
        ]
        self.assertEqual(logs.parse(ENTRY, "\n".join(lines)).observations, [])


class SnapshotTests(unittest.TestCase):
    def test_sql_inventory_scope_and_coverage(self):
        script = """
        CREATE TABLE snapshot_scope (origin_system TEXT, captured_at TEXT);
        CREATE TABLE customer_profiles (resource_id TEXT, customer_reference TEXT, full_name TEXT, email TEXT,
          phone TEXT, email_hash TEXT, account_status TEXT, updated_at TEXT);
        CREATE TABLE customer_exports (resource_id TEXT, customer_reference TEXT, owner_email TEXT,
          owner_phone TEXT, object_key TEXT, updated_at TEXT);
        INSERT INTO snapshot_scope VALUES ('account_service', '2026-01-02T03:04:05Z');
        INSERT INTO customer_profiles VALUES ('account_1', NULL, NULL, 'P@X.IO', NULL, NULL, 'ACTIVE', 't');
        """
        result = sql.parse(ENTRY, script)
        self.assertEqual([o.resource_id for o in result.observations], ["account_1"])
        cats = {(c.system_id, c.category) for c in result.coverages}
        self.assertIn(("account_service", "USER_PROFILE"), cats)
        self.assertNotIn(("export_service", "USER_EXPORT"), cats)  # not in scope -> unknown, not absent

    def test_sql_replica_drift(self):
        script = """
        CREATE TABLE customer_profiles_primary (resource_id TEXT, user_id TEXT, full_name TEXT, email TEXT,
          phone TEXT, account_status TEXT, updated_at TEXT);
        CREATE TABLE customer_profiles_failover_replica (resource_id TEXT, user_id TEXT, full_name TEXT,
          email TEXT, phone TEXT, account_status TEXT, updated_at TEXT);
        INSERT INTO customer_profiles_failover_replica VALUES ('account_9','user_9','N','n@x.io','+1 555 0100',
          'ACTIVE','t');
        """
        result = sql.parse(ENTRY, script)
        self.assertEqual({o.instance for o in result.observations}, {"failover_replica"})
        primary = [c for c in result.coverages if c.instance == "primary"]
        self.assertTrue(primary and "account_9" not in primary[0].present)

    def test_json_bundle_empty_collection_is_coverage(self):
        doc = ('{"exported_at":"2026-01-02T00:00:00Z","snapshots":[{"captured_at":"2026-01-02T00:00:00Z",'
               '"data_store":"account_service","collection":"customer_profiles","records":[]}]}')
        result = json_records.parse(ENTRY, doc)
        self.assertEqual(len(result.coverages), 1)
        self.assertEqual(result.coverages[0].present, frozenset())

    def test_handover_text_rows(self):
        row = "- 2026-01-01T00:00:00Z | analytics_platform | analytics_1 | ANALYTICS_PROFILE | ANONYMIZED | x"
        obs = text.parse(ENTRY, row).observations[0]
        self.assertTrue(obs.exists)
        self.assertFalse(obs.exposed)


class UnknownLayoutTests(unittest.TestCase):
    def test_unrecognized_json_falls_back_to_document_reading(self):
        from audit.evidence import documents

        doc = '{"weird": {"rows": [{"id": "search_42", "owner": "p@x.io"}]}}'
        self.assertEqual(json_records.parse(ENTRY, doc).observations, [])
        fallback = documents.parse_unstructured_text(ENTRY, doc, None, "model")
        self.assertEqual([o.resource_id for o in fallback.observations], ["search_42"])
        self.assertIn(("email", "p@x.io"), fallback.observations[0].link_ids)


class NoHardcodedLabelsTest(unittest.TestCase):
    """Challenge rule: no case ids, evidence file ids or sample answers in the solution code."""

    def test_source_has_no_dataset_ids(self):
        pattern = re.compile(r"\b(case_\d{2,}|evidence_\d{2,}|activity_\d+|audit_\d{2,})\b")
        offenders = []
        for path in (CODE_DIR / "audit").rglob("*.py"):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    offenders.append(f"{path.name}:{n}: {line.strip()}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
