"""State of a resource at audit_at, and the evidence that proves it.

Rule (reproduces every evidence id cited in the sample answers):
1. Only evidence available at audit_at counts: the observation's own time and
   its file's capture time must both be <= audit_at.
2. The latest explicit observation decides. When one snapshot holds the record
   in several instances (primary and replicas), it is present if any instance
   still has it: a replica ghost is still personal data.
3. With no explicit observation, the latest complete snapshot (coverage) of the
   resource's system and category decides: not listed means absent. Empty
   snapshots (no rows at all) are not trusted as proof.
4. With neither, a record may still be *known* from a row timestamped <= audit_at
   inside an export captured later. Such a state is marked not citable: it may
   only support a future check (a retained record must still be present), never
   a finding or a COMPLETE verification, because no evidence existed at audit_at.
5. Otherwise the state is unknown and the resource produces no step.
"""

from __future__ import annotations

from .index import EvidenceIndex
from .models import ResourceState


def _usable(index: EvidenceIndex, evidence_id: str, observed_at: str, audit_at: str) -> bool:
    entry = index.files.get(evidence_id)
    captured = entry.captured_at if entry else observed_at
    return observed_at <= audit_at and captured <= audit_at


def _merge(values) -> bool | None:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return any(vals)


def resolve_state(index: EvidenceIndex, resource_id: str, audit_at: str) -> ResourceState | None:
    observations = [o for o in index.by_resource.get(resource_id, [])
                    if _usable(index, o.evidence_id, o.observed_at, audit_at)]
    meta = index.resource_meta.get(resource_id)
    if observations:
        latest = max(observations, key=lambda o: (o.observed_at, index.files[o.evidence_id].captured_at
                                                  if o.evidence_id in index.files else "", o.evidence_id))
        group = [o for o in observations
                 if o.evidence_id == latest.evidence_id and o.observed_at == latest.observed_at]
        exists = _merge(o.exists for o in group)
        present = [o for o in group if o.exists]
        exposed = _merge(o.exposed for o in present) if present else None
        active = _merge(o.active for o in present) if present else None
        category = next((o.category for o in group if o.category), meta[1] if meta else None)
        system = next((o.system_id for o in group if o.system_id), meta[0] if meta else None)
        details = tuple(d for o in group for d in o.details)
        return ResourceState(system, resource_id, category, exists, exposed, active,
                             latest.evidence_id, latest.observed_at, "explicit", details)

    if not meta:
        return None
    system, category = meta
    coverages = [c for c in index.coverage_by_key.get((system, category), [])
                 if c.snapshot_rows > 0 and _usable(index, c.evidence_id, c.observed_at, audit_at)]
    known = [o for o in index.by_resource.get(resource_id, []) if o.observed_at <= audit_at]
    late = max(known, key=lambda o: (o.observed_at, o.evidence_id)) if known else None
    # A row listing the record at the same moment a coverage omits it means the record existed.
    if late and (not coverages or late.observed_at >= max(c.observed_at for c in coverages)):
        return ResourceState(late.system_id or system, resource_id, late.category or category, late.exists,
                             late.exposed, late.active, late.evidence_id, late.observed_at, "known_late",
                             late.details)
    if not coverages:
        return None
    latest = max(coverages, key=lambda c: (c.observed_at, c.evidence_id))
    same_snapshot = [c for c in coverages if c.evidence_id == latest.evidence_id and c.observed_at == latest.observed_at]
    listed = any(resource_id in c.present for c in same_snapshot)
    return ResourceState(system, resource_id, category, listed, None, None,
                         latest.evidence_id, latest.observed_at, "coverage")
