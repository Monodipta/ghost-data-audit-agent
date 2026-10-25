"""Stage A: parse every evidence file once and index the results.

The index answers two questions for any case:
- which resources carry one of these identifiers?      (identifier -> resources)
- what do we know about this resource, over time?      (resource -> observations)
plus complete-snapshot coverage, used to prove absence of records a snapshot
does not list.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import activity as activity_mod
from .config import EVIDENCE_DIR, DATASET_DIR, Settings
from .evidence import documents, json_records, logs, sql, text
from .llm.gateway import Gateway
from .loaders import evidence_manifest, read_csv
from .models import Coverage, EvidenceFile, Observation, ParseResult

log = logging.getLogger(__name__)

PARSERS = {".sql": sql.parse, ".json": json_records.parse, ".log": logs.parse, ".txt": text.parse}


@dataclass
class EvidenceIndex:
    files: dict[str, EvidenceFile]
    observations: list[Observation]
    coverages: list[Coverage]
    activity: list[activity_mod.ActivityEvent]
    warnings: list[str]
    by_resource: dict[str, list[Observation]] = field(default_factory=dict)
    by_identifier: dict[tuple, set[str]] = field(default_factory=dict)
    coverage_by_key: dict[tuple, list[Coverage]] = field(default_factory=dict)
    activity_by_resource: dict[str, list] = field(default_factory=dict)
    resource_meta: dict[str, tuple] = field(default_factory=dict)  # resource -> (system, category)

    def build_maps(self) -> None:
        by_resource = defaultdict(list)
        by_identifier = defaultdict(set)
        for obs in self.observations:
            by_resource[obs.resource_id].append(obs)
            for ident in obs.link_ids:
                by_identifier[ident].add(obs.resource_id)
        for ev in self.activity:
            for ident in ev.link_ids:
                by_identifier[ident].add(ev.resource_id)
        for lst in by_resource.values():
            lst.sort(key=lambda o: (o.observed_at, o.evidence_id))
        cov = defaultdict(list)
        for c in self.coverages:
            cov[(c.system_id, c.category)].append(c)
        for lst in cov.values():
            lst.sort(key=lambda c: (c.observed_at, c.evidence_id))
        act = defaultdict(list)
        for ev in self.activity:
            act[ev.resource_id].append(ev)
        meta = {}
        for ev in self.activity:
            if ev.category:
                meta[ev.resource_id] = (ev.system_id, ev.category)
        for rid, lst in by_resource.items():  # evidence wins over activity for metadata
            known = [o for o in lst if o.category]
            if known:
                meta[rid] = (known[-1].system_id, known[-1].category)
        self.by_resource, self.by_identifier = dict(by_resource), dict(by_identifier)
        self.coverage_by_key, self.activity_by_resource, self.resource_meta = dict(cov), dict(act), meta


def _parse_file(entry: EvidenceFile, gateway: Gateway | None, settings: Settings) -> ParseResult:
    path = EVIDENCE_DIR.parent / entry.path
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            return documents.parse_pdf(entry, path, gateway, settings.vision_model)
        if suffix in (".png", ".jpg", ".jpeg"):
            return documents.parse_image(entry, path, gateway, settings.vision_model)
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ParseResult(warnings=[f"{entry.file_id}: unsupported binary file type {suffix}"])
        parser = PARSERS.get(suffix)
        result = parser(entry, content) if parser else ParseResult()
        if not result.observations and not result.coverages and content.strip():
            # New layout or unknown file type: let the model describe it, code validates.
            log.info("%s: no deterministic parser matched (%s); using model extraction", entry.file_id, suffix)
            fallback = documents.parse_unstructured_text(entry, content, gateway, settings.vision_model)
            fallback.warnings = [w for w in result.warnings if "unrecognized" not in w] + fallback.warnings
            return fallback
        return result
    except Exception as exc:  # one bad file must not stop the run
        return ParseResult(warnings=[f"{entry.file_id}: parse failed: {type(exc).__name__}: {exc}"])


def _resolve_named(observations: list[Observation], events: list) -> list[Observation]:
    """Replace named-object placeholders (e.g. a file shown in a storage browser) with the resource the
    activity catalog says carries that name. Names nobody catalogued are dropped."""
    by_alias = {ev.alias.lower(): ev for ev in events if ev.alias}
    out = []
    for obs in observations:
        if not obs.resource_id.startswith(documents.NAMED_PREFIX):
            out.append(obs)
            continue
        ev = by_alias.get(obs.resource_id[len(documents.NAMED_PREFIX):])
        if ev:
            out.append(Observation(obs.evidence_id, obs.observed_at, ev.system_id, ev.resource_id, ev.category,
                                   obs.exists, None, None, frozenset(), details=obs.details))
    return out


def build_index(settings: Settings, gateway: Gateway | None, workers: int = 4) -> EvidenceIndex:
    manifest = evidence_manifest(DATASET_DIR)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda e: _parse_file(e, gateway, settings), manifest))
    merged = ParseResult()
    for r in results:
        merged.extend(r)
    events = activity_mod.parse(read_csv("system_activity.csv"))
    observations = _resolve_named(merged.observations, events)
    index = EvidenceIndex(
        files={e.file_id: e for e in manifest},
        observations=observations,
        coverages=merged.coverages,
        activity=events,
        warnings=merged.warnings,
    )
    index.build_maps()
    for w in merged.warnings:
        log.warning(w)
    return index
