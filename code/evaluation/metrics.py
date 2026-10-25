"""Scoring of predicted rows against expected rows.

- status accuracy: deletion_status matches.
- step-level: each step is compared as a whole (phase, system_id, resource_id,
  operation, state, evidence_id; step_no ignored). Micro precision / recall / F1
  over all steps, plus the share of cases whose step set matches exactly.
- field-level: steps are aligned by (system_id, resource_id, operation); for each
  expected step, each field counts as correct only if an aligned predicted step
  has the same value (missing steps count as wrong).
- sequence: the ordered list of steps (including step_no) matches exactly, and the
  mean longest-common-subsequence ratio of the ordered step lists.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

FIELDS = ("phase", "system_id", "resource_id", "operation", "state", "evidence_id")


def _key(step: dict) -> tuple:
    return tuple(step.get(f, "") for f in FIELDS)


def _lcs(a: list, b: list) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1]))
        prev = cur
    return prev[-1]


@dataclass
class CaseScore:
    case_id: str
    expected_status: str
    predicted_status: str
    tp: int
    fp: int
    fn: int
    exact_steps: bool
    exact_sequence: bool
    lcs_ratio: float
    missing: list = field(default_factory=list)
    extra: list = field(default_factory=list)


def score_case(case_id: str, exp_status: str, exp_steps: list, pred_status: str, pred_steps: list) -> CaseScore:
    e, p = Counter(map(_key, exp_steps)), Counter(map(_key, pred_steps))
    tp = sum((e & p).values())
    missing = sorted((e - p).elements())
    extra = sorted((p - e).elements())
    exact_seq = [_key(s) + (s.get("step_no"),) for s in exp_steps] == [_key(s) + (s.get("step_no"),) for s in pred_steps]
    denom = max(len(exp_steps), len(pred_steps))
    lcs = _lcs(list(map(_key, exp_steps)), list(map(_key, pred_steps))) / denom if denom else 1.0
    return CaseScore(case_id, exp_status, pred_status, tp, sum(p.values()) - tp, sum(e.values()) - tp,
                     not missing and not extra, exact_seq, lcs, missing, extra)


def field_accuracy(pairs: list[tuple[list, list]]) -> dict[str, float]:
    """pairs: (expected_steps, predicted_steps) per case."""
    correct, total = Counter(), 0
    for exp, pred in pairs:
        index = {}
        for s in pred:
            index.setdefault((s.get("system_id"), s.get("resource_id"), s.get("operation")), s)
        for s in exp:
            total += 1
            match = index.get((s.get("system_id"), s.get("resource_id"), s.get("operation")))
            for f in FIELDS:
                if match is not None and match.get(f) == s.get(f):
                    correct[f] += 1
    return {f: (correct[f] / total if total else 1.0) for f in FIELDS}


def positional_field_accuracy(pairs: list[tuple[list, list]]) -> dict[str, float]:
    """Step i of the expected list against step i of the predicted list, per field.
    Lengths are padded, so missing or extra steps count as wrong. Sensitive to order."""
    correct, total = Counter(), 0
    for exp, pred in pairs:
        n = max(len(exp), len(pred))
        total += n
        for i in range(n):
            e = exp[i] if i < len(exp) else {}
            p = pred[i] if i < len(pred) else {}
            for f in FIELDS + ("step_no",):
                if e and p and e.get(f) == p.get(f):
                    correct[f] += 1
    return {f: (correct[f] / total if total else 1.0) for f in FIELDS + ("step_no",)}


def citation_accuracy(pairs: list[tuple[list, list]]) -> tuple[int, int]:
    """Among expected steps we also produced (same phase, system, resource, operation), how many cite
    exactly the expected evidence_id (including the empty id for future work)."""
    hit = total = 0
    for exp, pred in pairs:
        index = {(s.get("phase"), s.get("system_id"), s.get("resource_id"), s.get("operation")): s for s in pred}
        for s in exp:
            match = index.get((s.get("phase"), s.get("system_id"), s.get("resource_id"), s.get("operation")))
            if match is not None:
                total += 1
                hit += match.get("evidence_id") == s.get("evidence_id")
    return hit, total


def summarize(scores: list[CaseScore], pairs: list[tuple[list, list]]) -> dict:
    n = len(scores)
    tp, fp, fn = (sum(getattr(s, k) for s in scores) for k in ("tp", "fp", "fn"))
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "cases": n,
        "status_accuracy": sum(s.expected_status == s.predicted_status for s in scores) / n if n else 0,
        "step_precision": precision,
        "step_recall": recall,
        "step_f1": f1,
        "exact_step_set": sum(s.exact_steps for s in scores) / n if n else 0,
        "exact_sequence": sum(s.exact_sequence for s in scores) / n if n else 0,
        "mean_lcs_ratio": sum(s.lcs_ratio for s in scores) / n if n else 0,
        "field_accuracy": field_accuracy(pairs),
        "positional_field_accuracy": positional_field_accuracy(pairs),
        "citation": citation_accuracy(pairs),
        "steps": {"tp": tp, "fp": fp, "fn": fn},
    }
