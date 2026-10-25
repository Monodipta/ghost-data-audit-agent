"""Write code/evaluation/usage_report.md for the full-dataset run that produced output.csv.

Every model answer used by the run is counted, whether it was fetched live in
this run or served from the cache (a cached answer still cost tokens once, when
it was first produced). Cost is estimated at paid list prices; the actual cost
on the Gemini free tier is $0.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .config import CODE_DIR

REPORT_PATH = CODE_DIR / "evaluation" / "usage_report.md"

# USD per 1M tokens (input, output). Thinking tokens are billed as output.
PRICES = {
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.7-flash": (0.75, 3.75),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
}
PRICE_NOTES = [
    "gemini-3.5-flash-lite $0.30 / $2.50 and gemini-3.5-flash $1.50 / $9.00: third-party price trackers citing "
    "the Gemini API pricing page (Aug-Sep 2026).",
    "gemini-3.7-flash $0.75 / $3.75: Google Cloud introductory price through 2026-12-31 (standard $1.50 / $7.50 "
    "from 2027).",
    "gemini-2.5-flash $0.30 / $2.50 and gemini-2.5-flash-lite $0.10 / $0.40: Gemini API list prices at their "
    "2025 release. gemini-3.1-flash-lite has no verified price and is shown as 'not priced'. Fallback models "
    "are only used when a preferred model's daily free quota is exhausted.",
]


def _cost(model: str, inp: int, out: int) -> float | None:
    if model not in PRICES:
        return None
    pi, po = PRICES[model]
    return inp / 1e6 * pi + out / 1e6 * po


def write_usage_report(usage: dict, tasks: dict, n_requests: int, offline: bool, output_path: Path) -> Path:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows, tot = [], {"answers": 0, "live": 0, "in": 0, "out": 0, "cost": 0.0}
    for model, u in sorted(usage.items()):
        answers = u["calls"] + u["cached_calls"]
        out_tokens = u["output_tokens"] + u["thinking_tokens"]
        cost = _cost(model, u["input_tokens"], out_tokens)
        rows.append((model, ", ".join(sorted(k for k in tasks.get(model, ()) if k)), answers, u["calls"],
                     u["input_tokens"], out_tokens, cost))
        tot["answers"] += answers
        tot["live"] += u["calls"]
        tot["in"] += u["input_tokens"]
        tot["out"] += out_tokens
        tot["cost"] += cost or 0.0
    total_tokens = tot["in"] + tot["out"]
    per_req = lambda x: x / n_requests if n_requests else 0  # noqa: E731

    lines = [
        "# Token Usage and Cost Report",
        "",
        f"Final full-dataset run that produced `{output_path.name}`: {n_requests} requests from "
        f"`dataset/deletion_requests.csv`, generated {now} "
        f"({'offline, every model answer served from the cache' if offline else 'online'}).",
        "",
        "**Provider:** Google Gemini API (`google-genai` SDK), temperature 0, JSON response schema.",
        "",
        "## Per-model totals",
        "",
        "| Model | Used for | Model answers used | Live calls this run | Input tokens | Output tokens (incl. thinking) "
        "| Total tokens | Estimated cost (USD) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for model, used_for, answers, live, inp, out, cost in rows:
        lines.append(f"| {model} | {used_for} | {answers} | {live} | {inp:,} | {out:,} | {inp + out:,} | "
                     + (f"${cost:.4f}" if cost is not None else "not priced") + " |")
    lines += [
        f"| **Overall** | | **{tot['answers']}** | **{tot['live']}** | **{tot['in']:,}** | **{tot['out']:,}** | "
        f"**{total_tokens:,}** | **${tot['cost']:.4f}** |",
        "",
        "## Per request",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Requests | {n_requests} |",
        f"| Model answers per request | {per_req(tot['answers']):.3f} |",
        f"| Input tokens per request | {per_req(tot['in']):,.1f} |",
        f"| Output tokens per request | {per_req(tot['out']):,.1f} |",
        f"| Total tokens per request | {per_req(total_tokens):,.1f} |",
        f"| Estimated cost per request (USD) | ${per_req(tot['cost']):.6f} |",
        f"| Estimated total cost (USD) | ${tot['cost']:.4f} |",
        "| Actual cost (Gemini free tier) | $0.00 |",
        "",
        "## Why usage is this low",
        "",
        "- The model is used only where language or vision is needed: request intent (distinct texts, about 20 per "
        "call) and documents without a fixed layout (PDFs and screenshots, one call each, plus a named-object pass "
        "for documents with no record ids). Every SQL, JSON, log and text file is parsed by code.",
        "- Every answer is cached by a hash of model, prompt, schema and input, so re-runs cost nothing and give "
        "byte-identical output.",
        "- Document extraction is shared by all cases: its cost does not grow with the number of requests.",
        "",
        "## Price sources",
        "",
        *[f"- {n}" for n in PRICE_NOTES],
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return REPORT_PATH
