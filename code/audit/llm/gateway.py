"""Gemini gateway.

Every model call goes through `Gateway.generate_json`, which:
- returns a cached answer when the same (model, prompt, input) was seen before;
- otherwise calls Gemini with temperature 0 and a JSON response schema;
- retries transient failures with exponential backoff;
- records token usage per model for the usage report.

The cache makes runs reproducible and lets a run complete offline.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from ..config import CACHE_DIR, Settings


log = logging.getLogger(__name__)

# Quota ids look like "GenerateRequestsPerDayPerProjectPerModel-FreeTier".
DAILY_QUOTA_RE = re.compile(r"PerDay|per day|daily", re.IGNORECASE)


class LLMUnavailable(RuntimeError):
    """No cached answer and no way to call a model (offline, no key, or quota exhausted)."""


class DailyQuotaExhausted(RuntimeError):
    """The model's daily request quota is used up; retrying today will not help."""


@dataclass
class ModelUsage:
    calls: int = 0
    cached_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0


@dataclass
class UsageMeter:
    by_model: dict[str, ModelUsage] = field(default_factory=dict)
    tasks: dict[str, set] = field(default_factory=dict)  # model -> kinds of work it did (intent, documents, ...)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, model: str, usage: dict, cached: bool, kind: str = "") -> None:
        with self.lock:
            self.tasks.setdefault(model, set()).add(kind)
            m = self.by_model.setdefault(model, ModelUsage())
            if cached:
                m.cached_calls += 1
            else:
                m.calls += 1
            m.input_tokens += usage.get("input_tokens", 0)
            m.output_tokens += usage.get("output_tokens", 0)
            m.thinking_tokens += usage.get("thinking_tokens", 0)

    def as_dict(self) -> dict:
        return {k: vars(v) for k, v in sorted(self.by_model.items())}


class RateLimiter:
    """At most `rpm` requests per rolling minute, per model, across threads."""

    def __init__(self, rpm: int):
        self.rpm = max(1, rpm)
        self.sent: dict[str, deque] = {}
        self.lock = threading.Lock()

    def wait(self, model: str) -> None:
        while True:
            with self.lock:
                q = self.sent.setdefault(model, deque())
                now = time.monotonic()
                while q and now - q[0] >= 60:
                    q.popleft()
                if len(q) < self.rpm:
                    q.append(now)
                    return
                sleep_for = 60 - (now - q[0]) + 0.5
            time.sleep(sleep_for)


RETRY_IN_RE = re.compile(r"retry in ([\d.]+)s|retryDelay['\"]?:\s*['\"](\d+)s", re.IGNORECASE)


def _retry_delay(exc: Exception, fallback: float) -> float:
    """Use the server's suggested delay for quota errors, else the backoff value."""
    m = RETRY_IN_RE.search(str(exc))
    if m:
        return float(m.group(1) or m.group(2)) + 1
    return fallback


class Gateway:
    def __init__(self, settings: Settings, cache_dir: Path = CACHE_DIR, max_retries: int = 6,
                 rpm: int | None = None):
        self.settings = settings
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_retries = max_retries
        self.limiter = RateLimiter(rpm or int(os.environ.get("LLM_RPM", "4")))
        self.usage = UsageMeter()
        self.exhausted: set[str] = set()  # models whose daily quota ran out in this run
        self.used_cache: set[Path] = set()  # cache files read or written in this run
        self.lock = threading.Lock()
        self._client = None

    # -- cache -------------------------------------------------------------
    @staticmethod
    def cache_key(model: str, prompt: str, payload: bytes) -> str:
        h = hashlib.sha256()
        for part in (model.encode(), b"\0", prompt.encode(), b"\0", payload):
            h.update(part)
        return h.hexdigest()

    def _cache_path(self, kind: str, key: str) -> Path:
        return self.cache_dir / kind / f"{key}.json"

    # -- model -------------------------------------------------------------
    def _get_client(self):
        if self._client is None:
            if self.settings.offline or not self.settings.api_key:
                raise LLMUnavailable("offline mode or GEMINI_API_KEY not set")
            from google import genai

            self._client = genai.Client(api_key=self.settings.api_key)
        return self._client

    def generate_json(
        self,
        kind: str,
        models: str | list[str],
        prompt: str,
        schema: dict,
        text: str | None = None,
        image: bytes | None = None,
        mime_type: str = "image/png",
        label: str = "",
    ) -> dict:
        """Return the model's JSON answer for prompt + (text or image).

        `models` is one model or a fallback chain ("a,b"). A cached answer from any
        model in the chain is reused. Live calls go to the first model whose daily
        quota is not exhausted.
        """
        chain = [m.strip() for m in (models.split(",") if isinstance(models, str) else models) if m.strip()]
        payload = image if image is not None else (text or "").encode("utf-8")
        signature = prompt + json.dumps(schema, sort_keys=True)
        for model in chain:
            path = self._cache_path(kind, self.cache_key(model, signature, payload))
            if path.exists():
                self.used_cache.add(path)
                cached = json.loads(path.read_text(encoding="utf-8"))
                self.usage.record(model, cached.get("usage", {}), cached=True, kind=kind)
                log.info("%s: cached (%s)", label or kind, model)
                return cached["answer"]

        client = self._get_client()
        last_error: Exception | None = None
        for model in chain:
            if model in self.exhausted:
                continue
            try:
                answer, usage = self._call(client, model, prompt, schema, text, image, mime_type, label or kind)
            except DailyQuotaExhausted as exc:
                with self.lock:
                    self.exhausted.add(model)
                log.warning("%s: daily quota exhausted for %s; trying next model", label or kind, model)
                last_error = exc
                continue
            except RuntimeError as exc:
                log.warning("%s: %s failed (%s); trying next model", label or kind, model, str(exc)[:120])
                last_error = exc
                continue
            path = self._cache_path(kind, self.cache_key(model, signature, payload))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"model": model, "usage": usage, "answer": answer},
                                       ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
            self.used_cache.add(path)
            self.usage.record(model, usage, cached=False, kind=kind)
            log.info("%s: extracted with %s", label or kind, model)
            return answer
        raise LLMUnavailable(f"no model available for {label or kind}: {last_error}")

    def _call(self, client, model, prompt, schema, text, image, mime_type, label):
        from google.genai import types

        parts = [types.Part.from_text(text=prompt)]
        if image is not None:
            parts.append(types.Part.from_bytes(data=image, mime_type=mime_type))
        elif text is not None:
            parts.append(types.Part.from_text(text=text))
        config = types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_json_schema=schema,
        )
        delay = 5.0
        for attempt in range(1, self.max_retries + 1):
            try:
                self.limiter.wait(model)
                resp = client.models.generate_content(model=model, contents=parts, config=config)
                answer = json.loads(resp.text)
                meta = resp.usage_metadata
                return answer, {
                    "input_tokens": getattr(meta, "prompt_token_count", 0) or 0,
                    "output_tokens": getattr(meta, "candidates_token_count", 0) or 0,
                    "thinking_tokens": getattr(meta, "thoughts_token_count", 0) or 0,
                }
            except Exception as exc:  # network, quota, malformed JSON
                message = str(exc)
                if "429" in message and DAILY_QUOTA_RE.search(message):
                    raise DailyQuotaExhausted(message[:300]) from exc
                if attempt == self.max_retries:
                    raise RuntimeError(f"failed after {attempt} attempts: {message[:200]}") from exc
                wait = _retry_delay(exc, delay)
                log.info("%s: %s attempt %d failed (%s); retrying in %.0fs",
                         label, model, attempt, message[:60].replace("\n", " "), wait)
                time.sleep(wait)
                delay = min(delay * 2, 90)
