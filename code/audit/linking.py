"""Which resources belong to a case?

Two sources, in order of strength:

1. Identifier links: an evidence observation (or an activity identity link) that
   carries one of the subject's strong identifiers (email, phone, email hash,
   user id). Only evidence available at audit_at counts, and evidence that
   belongs to an earlier deletion request by the same person is skipped.
2. Workflow links: resources that carry no identifiers at all (an account
   already deleted, an analytics profile already anonymized) are known only from
   the deletion workflow's own activity events, which run around the time the
   case was reported. Those candidates are assigned globally, so that every
   resource belongs to at most one case: identifier links win, then the case
   whose reported_at is nearest, and each case takes at most one resource per
   category this way.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .identity import IdentityResolver
from .index import EvidenceIndex
from .models import Identity, Request

WORKFLOW_SOURCE = "deletion_worker"
WINDOW_BEFORE = timedelta(hours=1, minutes=15)   # workflow events start shortly before the status report
WINDOW_AFTER = timedelta(hours=2)                # and may finish shortly after it
# A resource that audit-time evidence inspected counts as this much closer in time. Tuned on the public
# samples; it only matters when several cases compete for workflow events in the same window.
INSPECTED_BONUS_SECONDS = 30 * 60


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class CaseLinks:
    resources: dict[str, str] = field(default_factory=dict)  # resource_id -> how it was linked

    def add(self, resource_id: str, how: str) -> None:
        self.resources.setdefault(resource_id, how)


def _usable(index: EvidenceIndex, evidence_id: str, observed_at: str, audit_at: str) -> bool:
    """For linking, a fact counts if it was true at audit_at (row time), even if the export came later.
    Citing it as proof additionally needs the file to exist at audit_at (see state.py)."""
    return observed_at <= audit_at


def identifier_links(req: Request, ident: Identity, index: EvidenceIndex, after: str | None) -> CaseLinks:
    """Resources whose in-window evidence carries one of the subject's strong identifiers."""
    links = CaseLinks()
    strong = ident.strong_ids
    candidates: set[str] = set()
    for ident_key in strong:
        candidates |= index.by_identifier.get(ident_key, set())
    for rid in sorted(candidates):
        for obs in index.by_resource.get(rid, []):
            if after and obs.observed_at <= after:
                continue
            if obs.link_ids & strong and _usable(index, obs.evidence_id, obs.observed_at, req.audit_at):
                links.add(rid, f"identifier:{obs.evidence_id}")
                break
        else:
            for ev in index.activity_by_resource.get(rid, []):
                if ev.link_ids & strong and ev.event_time <= req.audit_at and not (after and ev.event_time <= after):
                    links.add(rid, f"identity_link:{ev.activity_id}")
                    break
    return links


def _other_owner(rid: str, subject: str | None, index: EvidenceIndex, resolver: IdentityResolver) -> bool:
    """True if any evidence ties this resource to a different person."""
    for obs in index.by_resource.get(rid, []):
        for ident in obs.link_ids:
            owner = resolver.owner_of(ident)
            if owner and owner != subject:
                return True
    return False


def link_all(requests: list[Request], identities: dict[str, Identity], index: EvidenceIndex,
             resolver: IdentityResolver) -> dict[str, CaseLinks]:
    """Link resources for every known request (the whole pool, so assignment is global)."""
    # An earlier request by the same person that was already audited before this one was made owns the
    # evidence up to its audit_at; this case only looks at what came after.
    by_user: dict[str, list[Request]] = defaultdict(list)
    for req in requests:
        by_user[identities[req.case_id].user_id or req.case_id].append(req)
    previous_audit: dict[str, str | None] = {}
    for reqs in by_user.values():
        for cur in reqs:
            earlier = [r.audit_at for r in reqs if r.case_id != cur.case_id and r.audit_at < cur.requested_at]
            previous_audit[cur.case_id] = max(earlier) if earlier else None

    links = {r.case_id: identifier_links(r, identities[r.case_id], index, previous_audit[r.case_id])
             for r in requests}
    identifier_owned = {rid for cl in links.values() for rid in cl.resources}

    # Workflow candidates, scored by distance to reported_at. A resource that audit-time evidence actually
    # inspected (e.g. a readback returning 404) gets a bonus over one nothing ever checked.
    workflow = [ev for ev in index.activity if ev.source_system == WORKFLOW_SOURCE and ev.category]
    candidates = []
    for req in requests:
        reported = _dt(req.reported_at)
        lo, hi = reported - WINDOW_BEFORE, reported + WINDOW_AFTER
        for ev in workflow:
            t = _dt(ev.event_time)
            if lo <= t <= hi and ev.resource_id not in identifier_owned:
                inspected = any(o.observed_at <= req.audit_at and o.observed_at >= req.reported_at
                                for o in index.by_resource.get(ev.resource_id, []))
                score = abs((t - reported).total_seconds()) - (INSPECTED_BONUS_SECONDS if inspected else 0)
                candidates.append((score, req.case_id, ev.resource_id, ev.category))
    candidates.sort()

    subject_of = {r.case_id: identities[r.case_id].user_id for r in requests}
    taken: set[str] = set()
    case_categories: dict[str, set] = defaultdict(set)
    for cl_case, cl in links.items():  # categories a case already has through identifiers
        for rid in cl.resources:
            meta = index.resource_meta.get(rid)
            if meta:
                case_categories[cl_case].add(meta[1])
    for _, case_id, rid, category in candidates:
        if rid in taken or category in case_categories[case_id]:
            continue
        if _other_owner(rid, subject_of[case_id], index, resolver):
            continue
        links[case_id].add(rid, "workflow_activity")
        taken.add(rid)
        case_categories[case_id].add(category)
    return links
