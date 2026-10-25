"""system_activity.csv: the global operations stream.

Activity rows are claims (a worker *says* it deleted something). They are kept
separate from evidence observations and used for three things:
- identity links  (LINK_RESOURCE_IDENTITY: resource -> email and user id),
- workflow context (which resources a deletion run touched, and when),
- recreation risks (RESTORE_BACKUP repopulating a downstream resource,
  CHECK_DATA_FLOW / CHECK_RESTORE_ACCESS reporting a live path).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import normalize as nz
from .evidence.records import category_for, system_for

USER_RE = re.compile(r"\buser_\d+\b")
RESTORE_RE = re.compile(r"repopulated downstream resource (\S+?)\.?$")


@dataclass(frozen=True)
class ActivityEvent:
    activity_id: str
    event_time: str
    event_type: str
    source_system: str
    target_system: str
    resource_id: str
    reported_result: str
    details: str
    category: str | None
    system_id: str | None
    link_ids: frozenset = frozenset()
    restored_resource: str | None = None
    alias: str | None = None  # a name the catalog gives the resource, e.g. a file name


def parse(rows: list[dict]) -> list[ActivityEvent]:
    events = []
    for r in rows:
        resource_id = r["resource_id"]
        category = category_for(None, resource_id=resource_id)
        target = r["target_system"]
        system = target if target in {
            "account_service", "search_service", "analytics_platform", "support_platform", "export_service",
            "integration_service", "backup_service", "security_service", "identity_service",
            "marketing_platform", "legal_service"} else system_for(None, category)
        if r["event_type"] in ("CHECK_DATA_FLOW", "DISABLE_DATA_FLOW"):
            system = "integration_service"
        link_ids = set()
        restored = None
        alias = None
        if r["event_type"] == "LINK_RESOURCE_IDENTITY":
            # Any wording: take every email and user id the catalog message names.
            link_ids |= {("email", e.rstrip(".").lower()) for e in nz.EMAIL_RE.findall(r["details"])}
            link_ids |= {("user", u) for u in USER_RE.findall(r["details"])}
            if (m := re.search(re.escape(resource_id) + r" \(([^)]+)\)", r["details"])) and m.group(1) != resource_id:
                alias = m.group(1).strip()
            if category is None and "attachment" in r["details"].lower():
                category = "SUPPORT_ATTACHMENT"
                system = target
        if r["event_type"] == "RESTORE_BACKUP" and (m := RESTORE_RE.search(r["details"])):
            restored = m.group(1)
        events.append(ActivityEvent(
            activity_id=r["activity_id"],
            event_time=nz.ts(r["event_time"]) or r["event_time"],
            event_type=r["event_type"],
            source_system=r["source_system"],
            target_system=target,
            resource_id=resource_id,
            reported_result=r["reported_result"],
            details=r["details"],
            category=category,
            system_id=system,
            link_ids=frozenset(link_ids),
            restored_resource=restored,
            alias=alias,
        ))
    return events
