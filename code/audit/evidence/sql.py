"""SQLite-compatible snapshot exports.

Layouts handled generically by inspecting each table's columns:
- envelope tables  (resource_id, origin_system, collection_name, record_json, updated_at)
  named customer_data_primary / customer_data_<replica>: one table per instance;
- flat typed tables (customer_profiles, support_records, ...) with an optional
  snapshot_scope table listing which systems the capture covered;
- flat tables with an instance suffix (customer_profiles_primary,
  customer_profiles_failover_replica, search_documents_primary).
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict

from .. import normalize as nz
from ..models import Coverage, EvidenceFile, ParseResult
from .records import category_for, from_record, system_for

INSTANCE_SUFFIXES = ("_primary", "_failover_replica", "_read_replica", "_reporting_replica")


def _instance_of(table: str) -> tuple[str, str]:
    """Split a table name into (collection, instance)."""
    if table.startswith("customer_data_"):
        rest = table[len("customer_data_"):]
        return "", rest or "primary"
    for suffix in INSTANCE_SUFFIXES:
        if table.endswith(suffix):
            base = table[: -len(suffix)]
            if base == "search_documents":
                base = "search_documents_primary"
            return base, suffix.lstrip("_")
    return table, "primary"


def _captured_at(text: str, fallback: str) -> str:
    for pattern in (r"Captured at:\s*(\S+)", r"snapshot_completed_at=(\S+)"):
        if (m := re.search(pattern, text)):
            if (value := nz.ts(m.group(1))):
                return value
    return nz.ts(fallback) or fallback


def parse(entry: EvidenceFile, text: str) -> ParseResult:
    result = ParseResult()
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(text)
    except sqlite3.Error as exc:
        result.warnings.append(f"{entry.file_id}: SQL error {exc}")
        return result
    conn.row_factory = sqlite3.Row
    captured = _captured_at(text, entry.captured_at)

    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    scope: dict[str, str] = {}
    if "snapshot_scope" in tables:
        for row in conn.execute("SELECT origin_system, captured_at FROM snapshot_scope"):
            scope[row[0]] = nz.ts(row[1]) or captured

    total_rows = 0
    # (instance, system, category) -> set of resource ids, for coverage
    listed: dict[tuple, set] = defaultdict(set)
    combos: set[tuple] = set()
    instances: set[str] = set()
    flat_tables: list[tuple[str, str, str]] = []

    for table in tables:
        if table == "snapshot_scope":
            continue
        cols = [c[1] for c in conn.execute(f'PRAGMA table_info("{table}")')]
        rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
        total_rows += len(rows)
        collection, instance = _instance_of(table)
        instances.add(instance)

        if "record_json" in cols:
            for row in rows:
                record = json.loads(row["record_json"])
                record.setdefault("resource_id", row["resource_id"])
                obs = from_record(entry.file_id, captured, row["origin_system"], row["collection_name"],
                                  record, instance=instance)
                if obs:
                    result.observations.append(obs)
                    key = (obs.system_id, obs.category)
                    combos.add(key)
                    listed[(instance,) + key].add(obs.resource_id)
            continue

        category = category_for(collection, resource_id="")
        system = system_for(None, category)
        flat_tables.append((instance, system, category))
        observed = scope.get(system, captured) if scope else captured
        for row in rows:
            record = dict(row)
            obs = from_record(entry.file_id, observed, system, collection, record, instance=instance)
            if obs:
                result.observations.append(obs)
                listed[(instance, obs.system_id, obs.category)].add(obs.resource_id)

    # Coverage: which (system, category) lists are complete at capture time.
    if scope:
        for instance, system, category in flat_tables:
            if system in scope and category:
                result.coverages.append(Coverage(
                    entry.file_id, scope[system], system, category, instance,
                    frozenset(listed.get((instance, system, category), set())), total_rows))
    elif flat_tables:
        for instance, system, category in flat_tables:
            if category:
                result.coverages.append(Coverage(
                    entry.file_id, captured, system, category, instance,
                    frozenset(listed.get((instance, system, category), set())), total_rows))
    for instance in sorted(i for i in instances if any(k[0] == i for k in listed) or combos):
        for system, category in sorted(combos, key=str):
            if category:
                result.coverages.append(Coverage(
                    entry.file_id, captured, system, category, instance,
                    frozenset(listed.get((instance, system, category), set())), total_rows))
    conn.close()
    return result
