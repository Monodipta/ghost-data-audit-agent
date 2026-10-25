"""Load the participant-facing CSV files from dataset/."""

from __future__ import annotations

import csv
from pathlib import Path

from .config import DATASET_DIR
from .models import EvidenceFile


def read_csv(name: str, dataset_dir: Path = DATASET_DIR) -> list[dict]:
    with open(dataset_dir / name, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def evidence_manifest(dataset_dir: Path = DATASET_DIR) -> list[EvidenceFile]:
    return [
        EvidenceFile(r["file_id"], r["file_path"], r["origin"], r["captured_at"])
        for r in read_csv("evidence_files.csv", dataset_dir)
    ]
