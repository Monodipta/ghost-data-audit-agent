"""Plain-text records, e.g. shift handovers with one pipe-delimited row per record:

- 2026-01-01T00:00:00Z | account_service | account_123 | USER_PROFILE | NOT_FOUND | person@example.com
"""

from __future__ import annotations

import re

from .. import normalize as nz
from ..models import EvidenceFile, ParseResult
from .records import from_result_row

ROW_RE = re.compile(r"^\s*-?\s*(\S+Z)\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*(.*?)\s*$")


def parse(entry: EvidenceFile, text: str) -> ParseResult:
    result = ParseResult()
    for line in text.splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        when, system, resource_id, record_type, state, ref = m.groups()
        obs = from_result_row(entry.file_id, nz.ts(when) or entry.captured_at, system, resource_id,
                              record_type, state, ref)
        if obs:
            result.observations.append(obs)
        else:
            result.warnings.append(f"{entry.file_id}: unknown state {state!r} for {resource_id}")
    return result
