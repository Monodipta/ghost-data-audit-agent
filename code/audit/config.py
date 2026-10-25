"""Paths and runtime settings. Everything is resolved from the repository root."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

CODE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = CODE_DIR.parent
DATASET_DIR = REPO_ROOT / "dataset"
EVIDENCE_DIR = DATASET_DIR / "evidence"
CACHE_DIR = CODE_DIR / ".cache"
TRACE_DIR = CODE_DIR / "traces"
OUTPUT_PATH = REPO_ROOT / "output.csv"

DEFAULT_INTENT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_VISION_MODEL = "gemini-3.5-flash"
# Tried in order when the preferred model's free-tier daily quota is exhausted.
INTENT_FALLBACKS = ("gemini-3.1-flash-lite", "gemini-2.5-flash-lite")
VISION_FALLBACKS = ("gemini-3.7-flash", "gemini-2.5-flash")


def _chain(preferred: str, fallbacks: tuple[str, ...]) -> str:
    models = [m.strip() for m in preferred.split(",") if m.strip()]
    models += [m for m in fallbacks if m not in models]
    return ",".join(models)


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    intent_model: str
    vision_model: str
    offline: bool


def load_settings(offline: bool = False) -> Settings:
    """Offline runs never read .env or the key: they use cached model answers only."""
    if not offline:
        load_dotenv(REPO_ROOT / ".env")
    key = None if offline else ((os.environ.get("GEMINI_API_KEY") or "").strip() or None)
    return Settings(
        api_key=key,
        intent_model=_chain(os.environ.get("INTENT_MODEL") or DEFAULT_INTENT_MODEL, INTENT_FALLBACKS),
        vision_model=_chain(os.environ.get("VISION_MODEL") or DEFAULT_VISION_MODEL, VISION_FALLBACKS),
        offline=offline,
    )
