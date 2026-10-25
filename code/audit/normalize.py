"""Normalization of identifiers, timestamps and empty values."""

from __future__ import annotations

import re
from datetime import datetime, timezone

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
USER_RE = re.compile(r"^user_\d+$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
NULLS = {"", "null", "none", "nil", "n/a", "no direct identifier"}


def clean(value):
    """Return None for empty or null-like values, else the stripped string."""
    if value is None:
        return None
    if isinstance(value, (bool, int, float)):
        return value
    text = str(value).strip().strip('"').strip()
    return None if text.lower() in NULLS else text


def email(value) -> str | None:
    text = clean(value)
    if not isinstance(text, str) or "@" not in text:
        return None
    match = EMAIL_RE.search(text)
    return match.group(0).rstrip(".").lower() if match else None


def phone(value) -> str | None:
    text = clean(value)
    if not isinstance(text, str):
        return None
    digits = re.sub(r"\D", "", text)
    return f"+{digits}" if len(digits) >= 7 else None


def name(value) -> str | None:
    text = clean(value)
    if not isinstance(text, str):
        return None
    return " ".join(text.split()).casefold()


def email_hash(value) -> str | None:
    text = clean(value)
    if not isinstance(text, str):
        return None
    text = text.lower()
    return text if HASH_RE.match(text) else None


def user_ref(value) -> str | None:
    text = clean(value)
    if not isinstance(text, str):
        return None
    text = text.lower()
    return text if USER_RE.match(text) else None


def reference(value) -> tuple[str, str] | None:
    """Classify a mixed reference field (email, user id, hash or phone)."""
    text = clean(value)
    if not isinstance(text, str):
        return None
    if (e := email(text)):
        return ("email", e)
    if (u := user_ref(text)):
        return ("user", u)
    if (h := email_hash(text)):
        return ("hash", h)
    if text.startswith("+") and (p := phone(text)):
        return ("phone", p)
    return None


def to_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = clean(value)
    if not isinstance(text, str):
        return None
    low = text.lower()
    if low in {"true", "1", "yes", "y", "enabled", "on"}:
        return True
    if low in {"false", "0", "no", "n", "disabled", "off"}:
        return False
    return None


def ts(value) -> str | None:
    """Normalize a timestamp to ISO-8601 UTC 'YYYY-MM-DDTHH:MM:SSZ'."""
    text = clean(value)
    if not isinstance(text, str):
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
