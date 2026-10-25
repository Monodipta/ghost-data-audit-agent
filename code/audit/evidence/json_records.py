"""JSON evidence exports.

Layouts, detected by their keys:
- snapshot bundle:   {"snapshots": [{captured_at, data_store, collection, records}]}
  Each snapshot lists a whole collection, so it is also a coverage. A collection
  named operational_record_history holds result-ledger rows instead.
- service export:    {"service_exports": {service: {lookup_type: [row, ...]}}}
  Each row carries its own observed_at.
- result ledger:     {"records": [{recorded_at, system, resource_id, record_type, result, ...}]}
- single capture:    {"captured_at", "collection", "records": [...]}
"""

from __future__ import annotations

import json

from .. import normalize as nz
from ..models import Coverage, EvidenceFile, ParseResult
from .records import category_for, from_record, from_result_row, system_for


def _ledger_rows(entry: EvidenceFile, rows: list, default_time: str, result: ParseResult) -> None:
    for row in rows:
        if not isinstance(row, dict) or "result" not in row:
            continue
        obs = from_result_row(
            entry.file_id,
            nz.ts(row.get("recorded_at")) or default_time,
            row.get("system"),
            str(row.get("resource_id")),
            row.get("record_type"),
            row.get("result"),
            row.get("subject_reference", row.get("lookup_value")),
        )
        if obs:
            result.observations.append(obs)


def _collection(entry, observed, system, collection, records, result, coverage: bool, total: int) -> None:
    category = category_for(collection)
    system_id = system_for(system, category)
    present = set()
    for rec in records:
        if not isinstance(rec, dict):
            continue
        obs = from_record(entry.file_id, observed, system_id, collection, rec)
        if obs:
            result.observations.append(obs)
            if obs.exists:
                present.add(obs.resource_id)
    if coverage and category:
        result.coverages.append(Coverage(entry.file_id, observed, system_id, category, "default",
                                         frozenset(present), total))


def parse(entry: EvidenceFile, text: str) -> ParseResult:
    result = ParseResult()
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        result.warnings.append(f"{entry.file_id}: invalid JSON {exc}")
        return result
    file_time = nz.ts(doc.get("captured_at") or doc.get("exported_at")) or nz.ts(entry.captured_at)

    if isinstance(doc.get("snapshots"), list):
        total = sum(len(s.get("records") or []) for s in doc["snapshots"])
        for snap in doc["snapshots"]:
            observed = nz.ts(snap.get("captured_at")) or file_time
            records = snap.get("records") or []
            if snap.get("collection") == "operational_record_history":
                _ledger_rows(entry, records, observed, result)
                continue
            _collection(entry, observed, snap.get("data_store"), snap.get("collection"), records,
                        result, coverage=True, total=total)
        return result

    if isinstance(doc.get("service_exports"), dict):
        for service, lookups in doc["service_exports"].items():
            if not isinstance(lookups, dict):
                continue
            for lookup_type, rows in lookups.items():
                for row in rows or []:
                    if not isinstance(row, dict):
                        continue
                    observed = nz.ts(row.get("observed_at")) or file_time
                    obs = from_record(entry.file_id, observed, service, lookup_type, row)
                    if obs is None:
                        continue
                    hits = row.get("hits")
                    if isinstance(hits, dict) and not (hits.get("total") or hits.get("documents")):
                        obs = obs.__class__(**{**obs.__dict__, "exists": False, "exposed": None})
                    result.observations.append(obs)
        return result

    records = doc.get("records")
    if isinstance(records, list):
        if records and isinstance(records[0], dict) and "result" in records[0]:
            _ledger_rows(entry, records, file_time, result)
        elif doc.get("collection"):
            _collection(entry, file_time, None, doc.get("collection"), records, result,
                        coverage=True, total=len(records))
        else:
            result.warnings.append(f"{entry.file_id}: unrecognized records layout")
        return result

    result.warnings.append(f"{entry.file_id}: unrecognized JSON layout")
    return result
