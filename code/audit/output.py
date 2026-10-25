"""Write output.csv exactly as the contract requires."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

HEADER = ["case_id", "deletion_status", "steps_json"]


def serialize_steps(steps: list[dict]) -> str:
    return json.dumps(steps, ensure_ascii=False, separators=(",", ":"))


def case_sort_key(case_id: str) -> tuple:
    """Numeric order of the trailing number (id 9 before id 10), matching deletion_requests.csv."""
    m = re.search(r"(\d+)$", case_id)
    return (case_id[: m.start()] if m else case_id, int(m.group(1)) if m else -1, case_id)


def write_output(rows: list[tuple[str, str, list[dict]]], path: Path) -> None:
    """rows: (case_id, status, steps). Written sorted by case_id, UTF-8, LF line endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(HEADER)
        for case_id, status, steps in sorted(rows, key=lambda r: case_sort_key(r[0])):
            writer.writerow([case_id, status, serialize_steps(steps)])
