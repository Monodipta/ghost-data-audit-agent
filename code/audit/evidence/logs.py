"""Operational log files.

One tokenizer handles every line style after the leading timestamp:
logfmt, pipe-delimited, bracketed, cloud (escaped logfmt inside message="..."),
syslog and JSON. Lines are grouped by trace id: the *_started line carries the
lookup key (who was looked up), the terminal line carries the resource and result.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

from .. import normalize as nz
from ..models import EvidenceFile, Observation, ParseResult
from .records import from_result_row, system_for

KV_RE = re.compile(r'([A-Za-z_][\w.]*)=("(?:[^"\\]|\\.)*"|\S+)')
TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s+(.*)$")

KEY_FIELDS = ("lookup_key", "match_key", "subject_key", "owner_key", "scan_key", "subject_ref",
              "correlation_key", "matched_value")
ID_FIELDS = ("email", "customer_email", "owner_email", "requester_email", "requester_name",
             "phone", "requester_phone", "email_hash", "customer_reference", "subject_reference")
SERVICE_ALIASES = {"profile_service": "account_service", "support_replica": "support_platform"}
INSTANCE_BY_SERVICE = {"support_replica": "replica"}

# event -> category (None = keep the default for the resource prefix)
TERMINAL_EVENTS = {
    "profile_lookup_completed": None,
    "index_query_completed": None,
    "audit_record_read_completed": None,
    "analytics_profile_read_completed": None,
    "analytics_profile_read": None,
    "analytics_identity_scan": None,
    "message_pii_scan": "SUPPORT_MESSAGE",
    "message_read": "SUPPORT_MESSAGE",
    "attachment_pii_scan": "SUPPORT_ATTACHMENT",
    "support_ticket_read_completed": "SUPPORT_MESSAGE",
    "connector_config_read_completed": "DATA_FLOW",
    "connector_heartbeat": "DATA_FLOW",
    "connector_config_loaded": "DATA_FLOW",
    "restore_policy_read_completed": "BACKUP_ARCHIVE",
    "restore_candidate_evaluated": "BACKUP_ARCHIVE",
    "restore_authorization_completed": "BACKUP_ARCHIVE",
    "export_download_check_completed": "USER_EXPORT",
    "export_metadata_read_completed": "USER_EXPORT",
    "retained_order_loaded": "LEGAL_HOLD_RECORD",
    "contact_lookup_completed": "SECONDARY_IDENTIFIER",
    "contact_query_completed": "SECONDARY_IDENTIFIER",
    "deletion_marker_check": "SECONDARY_IDENTIFIER",
}


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    return value.replace('\\"', '"')


def _kv(text: str) -> dict:
    return {k: _unquote(v) for k, v in KV_RE.findall(text)}


def tokenize(line: str) -> dict | None:
    """Parse one line into {ts, service, trace, event, level, **fields}."""
    m = TS_RE.match(line.strip())
    if not m:
        return None
    ts, rest = m.group(1), m.group(2)
    out: dict = {"ts": ts}
    if rest.startswith("{"):
        try:
            data = json.loads(rest)
        except json.JSONDecodeError:
            return None
        out.update({k: str(v) for k, v in data.items()})
        out.setdefault("level", data.get("severity"))
        out.setdefault("trace", data.get("trace_id"))
    elif rest.startswith("requestId="):
        fields = _kv(rest)
        inner = _kv(fields.pop("message", ""))
        out.update(fields)
        out.update(inner)
        out["trace"] = fields.get("requestId")
        out["service"] = fields.get("function")
    elif rest.startswith("<"):
        parts = rest.split(" ", 6)
        if len(parts) < 7:
            return None
        out["service"], out["trace"] = parts[2], parts[3]
        out.update(_kv(parts[6]))
    elif rest.startswith("["):
        m2 = re.match(r"\[(\w+)\]\s+\[([^\]]+)\]\s+\[([^\]]+)\]\s+([\w]+):\s*(.*)$", rest)
        if not m2:
            return None
        out["level"], out["service"], out["trace"], out["event"] = m2.group(1, 2, 3, 4)
        out.update(_kv(m2.group(5)))
    elif " | " in rest:
        parts = [p.strip() for p in rest.split(" | ", 4)]
        if len(parts) < 4:
            return None
        out["level"], out["service"], out["trace"], out["event"] = parts[:4]
        if len(parts) > 4:
            out.update(_kv(parts[4]))
    else:
        out.update(_kv(rest))
        out["trace"] = out.get("trace_id")
    out.setdefault("trace", out.get("trace_id"))
    return out


def _ids(event: dict, fields: tuple) -> set:
    ids = set()
    for f in fields:
        value = event.get(f)
        if f in ("requester_name",):
            if (n := nz.name(value)):
                ids.add(("name", n))
        elif f in ("phone", "requester_phone"):
            if (p := nz.phone(value)):
                ids.add(("phone", p))
        elif (ref := nz.reference(value)):
            ids.add(ref)
    return ids


def _int(value) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _state(event: dict) -> tuple[bool | None, bool | None, bool | None]:
    """(exists, exposed, active) for a terminal event."""
    name = event["event"]
    direct = bool(_ids(event, ("email", "customer_email", "owner_email", "requester_email",
                               "requester_name", "phone", "requester_phone", "email_hash")))
    if name == "profile_lookup_completed":
        rows, status = _int(event.get("rows")), event.get("http_status")
        exists = False if rows == 0 or status == "404" else True if rows or status == "200" else None
        return exists, (direct or None) if exists else None, None
    if name == "index_query_completed":
        hit = (event.get("result") or "").lower()
        exists = True if hit == "hit" else False if hit == "miss" else None
        if _int(event.get("total_hits")) == 0:
            exists = False
        return exists, None, None
    if name == "audit_record_read_completed":
        rows = _int(event.get("rows"))
        return (rows != 0) if rows is not None else True, None, None
    if name == "analytics_profile_read_completed":
        return True, direct, None
    if name == "analytics_profile_read":
        return True, (_int(event.get("direct_identifiers")) or 0) > 0, None
    if name in ("analytics_identity_scan", "message_pii_scan", "attachment_pii_scan"):
        return True, True, None
    if name == "message_read":
        text = event.get("message_text") or ""
        return True, ("[REDACTED]" not in text) or direct, None
    if name == "support_ticket_read_completed":
        return True, direct, None
    if name in ("connector_config_read_completed", "connector_heartbeat", "connector_config_loaded"):
        return True, None, nz.to_bool(event.get("enabled"))
    if name == "restore_policy_read_completed":
        present = nz.to_bool(event.get("archive_present"))
        return (present if present is not None else True), None, nz.to_bool(event.get("restore_allowed"))
    if name == "restore_candidate_evaluated":
        eligible = nz.to_bool(event.get("eligible"))
        blocked = nz.to_bool(event.get("deletion_block"))
        return True, None, bool(eligible) and not blocked
    if name == "restore_authorization_completed":
        return True, None, (event.get("decision") or "").lower() != "deny"
    if name in ("export_download_check_completed", "export_metadata_read_completed"):
        return nz.to_bool(event.get("available")), None, None
    if name == "retained_order_loaded":
        return True, None, None
    if name in ("contact_lookup_completed", "contact_query_completed"):
        rows = _int(event.get("rows"))
        exists = (rows > 0) if rows is not None else True
        return exists, True if exists else None, None
    if name == "deletion_marker_check":
        marker = nz.to_bool(event.get("marker_found"))
        return (not marker) if marker is not None else None, True if marker is False else None, None
    return None, None, None


def parse(entry: EvidenceFile, text: str) -> ParseResult:
    result = ParseResult()
    events = [e for e in (tokenize(line) for line in text.splitlines() if line.strip()) if e]
    by_trace: dict[str, list[dict]] = defaultdict(list)
    for i, ev in enumerate(events):
        by_trace[ev.get("trace") or f"__line{i}"].append(ev)

    for trace, evs in by_trace.items():
        keys: set = set()
        for ev in evs:
            keys |= _ids(ev, KEY_FIELDS)
        for ev in evs:
            name = ev.get("event") or ""
            resource_id = nz.clean(ev.get("resource_id"))
            if name == "record_lookup" and resource_id:
                obs = from_result_row(entry.file_id, ev["ts"], ev.get("system"), resource_id,
                                      ev.get("record_type"), ev.get("result"), ev.get("subject_reference"))
                if obs:
                    result.observations.append(obs)
                continue
            if name not in TERMINAL_EVENTS or not resource_id:
                continue
            exists, exposed, active = _state(ev)
            service = ev.get("service") or ""
            category = TERMINAL_EVENTS[name]
            from .records import category_for
            category = category or category_for(None, resource_id=resource_id)
            system = system_for(SERVICE_ALIASES.get(service, service) or None, category)
            link = keys | _ids(ev, ID_FIELDS)
            # A lookup key equal to a resource id is not a person identifier.
            link = {i for i in link if i[1] != resource_id}
            details = tuple((k, ev[k]) for k in ("event", "http_status", "rows", "enabled", "restore_allowed",
                                                 "retention_until", "event_code", "available") if k in ev)
            result.observations.append(Observation(
                evidence_id=entry.file_id,
                observed_at=ev["ts"],
                system_id=system,
                resource_id=resource_id,
                category=category,
                exists=exists,
                exposed=exposed,
                active=active,
                link_ids=frozenset(link),
                instance=INSTANCE_BY_SERVICE.get(service, "default"),
                details=details,
            ))
    return result
