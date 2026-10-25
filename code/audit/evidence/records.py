"""Turn a structured record (SQL row, JSON object) into an Observation.

All evidence formats describe the same kinds of records with different field
names. This module holds the one shared mapping, so each parser only needs to
find records and say which system and collection they came from.
"""

from __future__ import annotations

from .. import normalize as nz
from ..models import Observation

# Collection / table / record_type / lookup name -> deletion_rules data_category.
CATEGORY_BY_NAME = {
    "customer_profiles": "USER_PROFILE",
    "profile_lookups": "USER_PROFILE",
    "user_profile": "USER_PROFILE",
    "customer_profiles_primary": "USER_PROFILE",
    "customer_profiles_failover_replica": "USER_PROFILE",
    "customer_search_documents": "SEARCH_INDEX_ENTRY",
    "search_documents_primary": "SEARCH_INDEX_ENTRY",
    "index_queries": "SEARCH_INDEX_ENTRY",
    "search_index_entry": "SEARCH_INDEX_ENTRY",
    "customer_analytics_reports": "ANALYTICS_PROFILE",
    "customer_analytics_profiles": "ANALYTICS_PROFILE",
    "analytics_profile": "ANALYTICS_PROFILE",
    "profiles": "ANALYTICS_PROFILE",  # analytics_platform.profiles in service exports
    "support_conversations": "SUPPORT_MESSAGE",
    "support_message": "SUPPORT_MESSAGE",
    "support_records": "SUPPORT_MESSAGE",
    "tickets": "SUPPORT_MESSAGE",
    "ticket_attachments": "SUPPORT_ATTACHMENT",
    "support_attachment": "SUPPORT_ATTACHMENT",
    "customer_export_jobs": "USER_EXPORT",
    "customer_exports": "USER_EXPORT",
    "exports": "USER_EXPORT",
    "user_export": "USER_EXPORT",
    "connector_configurations": "DATA_FLOW",
    "connector_subscriptions": "DATA_FLOW",
    "connectors": "DATA_FLOW",
    "data_flow": "DATA_FLOW",
    "backup_catalog": "BACKUP_ARCHIVE",
    "backup_restore_entries": "BACKUP_ARCHIVE",
    "restore_entries": "BACKUP_ARCHIVE",
    "backup_archive": "BACKUP_ARCHIVE",
    "security_audit_events": "SECURITY_AUDIT_LOG",
    "security_audit_records": "SECURITY_AUDIT_LOG",
    "audit_records": "SECURITY_AUDIT_LOG",
    "security_audit_log": "SECURITY_AUDIT_LOG",
    "retained_order_records": "LEGAL_HOLD_RECORD",
    "legal_hold_record": "LEGAL_HOLD_RECORD",
    "deleted_customer_references": "ACCOUNT_TOMBSTONE",
    "account_tombstone": "ACCOUNT_TOMBSTONE",
    "marketing_profile": "MARKETING_PROFILE",
    "email_delivery_log": "EMAIL_DELIVERY_LOG",
    "cache_entry": "CACHE_ENTRY",
    "product_telemetry": "PRODUCT_TELEMETRY",
    "secondary_identifier": "SECONDARY_IDENTIFIER",
}

# Fallback by resource id prefix (support_ is ambiguous and resolved elsewhere).
CATEGORY_BY_PREFIX = {
    "account_": "USER_PROFILE",
    "search_": "SEARCH_INDEX_ENTRY",
    "analytics_": "ANALYTICS_PROFILE",
    "export_": "USER_EXPORT",
    "data_flow_": "DATA_FLOW",
    "backup_": "BACKUP_ARCHIVE",
    "audit_record_": "SECURITY_AUDIT_LOG",
    "legal_hold_": "LEGAL_HOLD_RECORD",
    "tombstone_": "ACCOUNT_TOMBSTONE",
    "marketing_": "MARKETING_PROFILE",
    "email_delivery_": "EMAIL_DELIVERY_LOG",
    "cache_": "CACHE_ENTRY",
    "telemetry_": "PRODUCT_TELEMETRY",
    "support_": "SUPPORT_MESSAGE",
}

# Base system that owns each category when the evidence does not name it.
SYSTEM_BY_CATEGORY = {
    "USER_PROFILE": "account_service",
    "SEARCH_INDEX_ENTRY": "search_service",
    "ANALYTICS_PROFILE": "analytics_platform",
    "SUPPORT_MESSAGE": "support_platform",
    "SUPPORT_ATTACHMENT": "support_platform",
    "USER_EXPORT": "export_service",
    "DATA_FLOW": "integration_service",
    "BACKUP_ARCHIVE": "backup_service",
    "SECURITY_AUDIT_LOG": "security_service",
    "LEGAL_HOLD_RECORD": "legal_service",
    "ACCOUNT_TOMBSTONE": "identity_service",
    "MARKETING_PROFILE": "marketing_platform",
}

SYSTEM_ALIASES = {"profile_service": "account_service"}

# Field names, grouped by the kind of identifier they hold.
EMAIL_FIELDS = ("email", "owner_email", "customer_email", "requester_email", "uploaded_by")
NAME_FIELDS = ("full_name", "display_name", "name", "requester_name")
PHONE_FIELDS = ("phone", "owner_phone", "requester_phone")
HASH_FIELDS = ("email_hash",)
USER_FIELDS = ("user_id", "customer_reference")
MIXED_FIELDS = ("subject_reference", "subject_selector", "lookup_value", "query", "subject_ref")
TEXT_FIELDS = ("message_text",)
NESTED_FIELDS = ("document", "profile")


def category_for(*names: str | None, resource_id: str = "") -> str | None:
    for raw in names:
        if raw:
            key = str(raw).strip().lower()
            if key in CATEGORY_BY_NAME:
                return CATEGORY_BY_NAME[key]
            if key.upper() in CATEGORY_BY_NAME.values():
                return key.upper()
    for prefix, category in CATEGORY_BY_PREFIX.items():
        if resource_id.startswith(prefix):
            return category
    return None


def system_for(system: str | None, category: str | None) -> str | None:
    if system:
        system = SYSTEM_ALIASES.get(system, system)
        return system
    return SYSTEM_BY_CATEGORY.get(category or "")


def extract_identifiers(record: dict) -> tuple[set, bool]:
    """Return (link ids, has_direct_identifier) for a record and its nested parts."""
    ids: set = set()
    direct = False

    def scan(rec: dict) -> None:
        nonlocal direct
        for f in EMAIL_FIELDS:
            if (e := nz.email(rec.get(f))):
                ids.add(("email", e))
                direct = True
        for f in NAME_FIELDS:
            if (n := nz.name(rec.get(f))):
                ids.add(("name", n))
                direct = True
        for f in PHONE_FIELDS:
            if (p := nz.phone(rec.get(f))):
                ids.add(("phone", p))
                direct = True
        for f in HASH_FIELDS:
            if (h := nz.email_hash(rec.get(f))):
                ids.add(("hash", h))
                direct = True
        for f in USER_FIELDS + MIXED_FIELDS:
            ref = nz.reference(rec.get(f))
            if ref:
                ids.add(ref)
                if ref[0] != "user":
                    direct = True
        for f in TEXT_FIELDS:
            text = nz.clean(rec.get(f))
            if isinstance(text, str):
                for match in nz.EMAIL_RE.findall(text):
                    ids.add(("email", match.rstrip(".").lower()))
                    direct = True
        for f in NESTED_FIELDS:
            if isinstance(rec.get(f), dict):
                scan(rec[f])
        hits = rec.get("hits")
        if isinstance(hits, dict):
            for doc in hits.get("documents") or []:
                if isinstance(doc, dict):
                    scan(doc)

    scan(record)
    return ids, direct


RESULT_STATES = {
    # result -> (exists, exposed, active)
    "FOUND": (True, None, None),
    "NOT_FOUND": (False, None, None),
    "IDENTIFIABLE": (True, True, None),
    "ANONYMIZED": (True, False, None),
    "REDACTED": (True, False, None),
    "ACTIVE": (True, None, True),
    "DISABLED": (True, None, False),
    "BLOCKED": (True, None, False),
}


def from_result_row(
    evidence_id: str,
    observed_at: str,
    system: str | None,
    resource_id: str,
    record_type: str | None,
    result: str | None,
    reference_value,
    instance: str = "default",
) -> Observation | None:
    """A ledger row that states a result directly (FOUND, NOT_FOUND, ACTIVE, ...)."""
    category = category_for(record_type, resource_id=resource_id)
    result = (nz.clean(result) or "").upper()
    if result not in RESULT_STATES:
        return None
    exists, exposed, active = RESULT_STATES[result]
    ref = nz.reference(reference_value)
    return Observation(
        evidence_id=evidence_id,
        observed_at=observed_at,
        system_id=system_for(system, category),
        resource_id=resource_id,
        category=category,
        exists=exists,
        exposed=exposed,
        active=active,
        link_ids=frozenset([ref] if ref else []),
        instance=instance,
        details=(("result", result),),
    )


def from_record(
    evidence_id: str,
    observed_at: str,
    system: str | None,
    collection: str | None,
    record: dict,
    instance: str = "default",
) -> Observation | None:
    """A raw stored record: its fields show what data it still holds."""
    resource_id = nz.clean(record.get("resource_id"))
    if not isinstance(resource_id, str):
        return None
    if record.get("storage_class") == "ticket_attachment" or "file_name" in record and "ticket_id" in record:
        collection = "ticket_attachments"
    category = category_for(collection, record.get("record_type"), resource_id=resource_id)
    system_id = system_for(system, category)
    ids, direct = extract_identifiers(record)

    exists: bool | None = True
    status = record.get("status_code")
    if status is not None and str(status) == "404":
        exists = False
    if "profile" in record and record.get("profile") is None and status is not None:
        exists = False if str(status) == "404" else exists

    exposed: bool | None = direct
    text = nz.clean(record.get("message_text"))
    if isinstance(text, str) and "[REDACTED]" in text and not direct:
        exposed = False

    active = None
    if category == "DATA_FLOW":
        active = nz.to_bool(record.get("enabled"))
    elif category == "BACKUP_ARCHIVE":
        active = nz.to_bool(record.get("restore_allowed"))

    details = []
    for key in ("account_status", "retention_until", "retained_until", "event_code", "event_name",
                "download_available", "expires_at", "last_delivery_status", "mode"):
        if record.get(key) is not None:
            details.append((key, str(record.get(key))))

    return Observation(
        evidence_id=evidence_id,
        observed_at=observed_at,
        system_id=system_id,
        resource_id=resource_id,
        category=category,
        exists=exists,
        exposed=exposed if exists else None,
        active=active,
        link_ids=frozenset(ids),
        instance=instance,
        details=tuple(details),
    )
