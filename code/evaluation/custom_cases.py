"""Custom evaluation cases created by the team.

Each case is a request plus the answer we derived by hand from the dataset and the
problem statement. A case that stands in for an existing sample ("twin") removes
that sample from global linking, so the two do not compete for the same resources.
"""

from __future__ import annotations

from dataclasses import dataclass

from audit.models import Request


@dataclass(frozen=True)
class CustomCase:
    request: Request
    expected_status: str
    expected_steps: list
    twin_of: str | None
    purpose: str
    reasoning: str


def _req(case_id, email, requested_at, reported_status, reported_at, audit_at, text) -> Request:
    return Request(case_id, email, requested_at, reported_status, reported_at, audit_at, text)


def _step(n, phase, system, resource, op, state, evidence):
    return {"step_no": n, "phase": phase, "system_id": system, "resource_id": resource, "operation": op,
            "state": state, "evidence_id": evidence}


CASES = [
    CustomCase(
        request=_req("custom_01", "novak.tomasz@icloud.com", "2026-09-09T12:00:00Z", "NOT_STARTED",
                     "2026-09-12T12:00:00Z", "2026-10-01T12:00:00Z",
                     "Please send me a copy of all the data you hold about me. Do not delete or change anything; "
                     "I want to keep using my account."),
        expected_status="NOT_APPLICABLE",
        expected_steps=[],
        twin_of=None,
        purpose="Negated deletion in English",
        reasoning="The text asks for a data copy and explicitly says not to delete. The subject has a real account "
                  "with remaining data, so a keyword or evidence-driven shortcut would wrongly audit it.",
    ),
    CustomCase(
        request=_req("custom_02", "amina.elmasri@gmail.com", "2026-08-18T09:14:00Z", "NOT_STARTED",
                     "2026-08-20T16:42:00Z", "2026-09-03T11:30:00Z",
                     "Quisiera recibir una copia de mis datos personales. Por favor, no borren nada de mi cuenta."),
        expected_status="NOT_APPLICABLE",
        expected_steps=[],
        twin_of=None,
        purpose="Non-deletion request in Spanish",
        reasoning="'I would like a copy of my personal data. Please do not erase anything from my account.' "
                  "This is an access request in another language with a negated deletion verb.",
    ),
    CustomCase(
        request=_req("custom_03", "NADIA.IONESCU@YAHOO.COM", "2026-08-31T15:42:00Z", "COMPLETE",
                     "2026-09-02T10:08:00Z", "2026-09-18T12:25:00Z",
                     "I used this Yahoo address before changing the email on my account. Please remove records "
                     "linked to both the old and current addresses."),
        expected_status="INCOMPLETE",
        expected_steps=[
            _step(1, "FINDING", "support_platform", "support_002", "REPORT_REMAINING_RECORD", "PRESENT", "evidence_61"),
            _step(2, "REMEDIATION", "support_platform", "support_002", "DELETE_RECORD", "ABSENT", ""),
            _step(3, "VERIFICATION", "account_service", "account_010", "VERIFY_RECORD_ABSENT", "ABSENT", ""),
            _step(4, "VERIFICATION", "support_platform", "support_002", "VERIFY_RECORD_ABSENT", "ABSENT", ""),
        ],
        twin_of="case_10",
        purpose="Historical email, written in upper case",
        reasoning="Same subject and dates as sample case_10, but the request email is the oldest address in a "
                  "three-step email chain and is upper-cased. Identity must be resolved case-insensitively "
                  "through the audit log; the answer must equal the published case_10 answer.",
    ),
    CustomCase(
        request=_req("custom_04", "leila.haddad@yahoo.com", "2026-08-27T14:17:00Z", "COMPLETE",
                     "2026-08-28T09:03:00Z", "2026-09-02T22:00:00Z",
                     "I deleted this account and received a confirmation, but the same email address is still "
                     "recognized. Please remove any remaining copy of my profile."),
        expected_status="COMPLETE",
        expected_steps=[
            _step(1, "VERIFICATION", "account_service", "account_005", "VERIFY_RECORD_ABSENT", "ABSENT", "evidence_10"),
        ],
        twin_of="case_05",
        purpose="Evidence after audit_at must be ignored",
        reasoning="Sample case_05 is INCOMPLETE because the failover replica captured at 2026-09-02T23:00 "
                  "(evidence_54) still holds the profile. Moving audit_at to 22:00 the same day hides that "
                  "capture. The latest complete account snapshot before then (evidence_10, 2026-08-27, primary "
                  "and read replica) does not list the profile, so at that time the deletion is proven complete.",
    ),
]
