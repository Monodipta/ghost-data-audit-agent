# PRD — Ghost Data Audit Agent

**Challenge:** HackerRank Orchestrate (October 2026), *Ghost Data Still Exists*
**Status:** Approved for build

---

## 1. Problem

Northstar Shop's deletion workflow reports requests as "Complete" while personal data still exists in replicas, search indexes, support records, analytics, exports, logs and backups. Active syncs and backup restores can also recreate data that was deleted at the source. Workflow statuses are claims, not proof.

We need an agent that audits each deletion request against the supplied evidence and policy and proves whether the deletion is actually complete.

## 2. Goals

For every request in `dataset/deletion_requests.csv`, the agent must:

1. Decide whether the request text authorizes deletion. If not, return `NOT_APPLICABLE` with `[]`.
2. Resolve the subject's current and historical identifiers (email, phone, name, email hash, `user_id`).
3. Find every relevant record, data flow and restore path, using only evidence available at or before `audit_at`.
4. Apply `deletion_rules.csv` to each record, including retained records and account tombstones.
5. Return `COMPLETE` with evidence-backed verification steps, or `INCOMPLETE` with findings, an ordered remediation plan and post-remediation checks.

## 3. Non-goals

- Executing remediation against real systems. The agent produces a plan only.
- Using organizer-only data, golden answers or per-case hardcoded labels.
- A user interface. The product is a command-line pipeline.

## 4. Users

| User | Need |
|---|---|
| Privacy / compliance reviewer | A trustworthy verdict per request, with the evidence behind it |
| Platform engineer | An ordered, safe remediation plan they can execute |
| Challenge evaluator | A reproducible `output.csv`, evaluation report and usage report |

## 5. Inputs

All from `dataset/`:

| File | Use |
|---|---|
| `deletion_requests.csv` | 518 cases to audit |
| `sample_deletion_requests.csv`, `sample_output.csv` | 32 labelled cases for evaluation only |
| `user_identities.csv`, `user_audit_log.csv` | Current and historical identifiers |
| `system_activity.csv` | Operational events (claims, identity links, restores) |
| `deletion_rules.csv` | Required treatment per data category |
| `evidence_files.csv` + `evidence/` | 94 evidence files: SQL, JSON, logs, TXT, PDF, PNG |

## 6. Output

`output.csv` at the repository root:

```text
case_id,deletion_status,steps_json
```

- Exactly 518 rows, sorted by `case_id`.
- `deletion_status` ∈ `COMPLETE`, `INCOMPLETE`, `NOT_APPLICABLE`.
- `steps_json` is a JSON array of steps (`step_no`, `phase`, `system_id`, `resource_id`, `operation`, `state`, `evidence_id`), ordered by phase, then operation order, then `system_id`, then `resource_id`.

## 7. Functional requirements

| ID | Requirement |
|---|---|
| FR-1 | Classify request intent across languages; non-deletion requests return `NOT_APPLICABLE`, `[]`. |
| FR-2 | Resolve the request email whether it is the current or a historical address. |
| FR-3 | Parse every evidence format into a common observation record. |
| FR-4 | Link records to the subject by exact identifier match only (decoys exist). |
| FR-5 | Determine each record's state at `audit_at`; ignore and never cite later evidence. |
| FR-6 | Treat workflow statuses and activity results as claims until evidence confirms them. |
| FR-7 | Detect ghost rows in replicas even when the primary has deleted them. |
| FR-8 | Report active data flows and restore risks; remediate them before dependent records. |
| FR-9 | Preserve records the policy requires to be retained, and verify they are still present. |
| FR-10 | Treat account tombstones as REDACT: keep `user_id`, remove direct identifiers. |
| FR-11 | Cite a participant-visible `file_id`, `activity_id` or `audit_id` for every finding and every `COMPLETE` verification. |
| FR-12 | Validate output schema, step numbering and ordering before writing. |
| FR-13 | Prove absence from complete snapshots (coverage) when no record-level "not found" exists. |
| FR-14 | Match hash-keyed records by hashing every current and historical email. |

## 8. Non-functional requirements

| Area | Requirement |
|---|---|
| Determinism | Same inputs produce byte-identical `output.csv`. LLM answers are cached by content hash. |
| Cost | LLM used only for intent and for PDFs/screenshots; intent batched (~20 texts per call). |
| Reproducibility | An `--offline` run from the shipped cache never reads `.env`, needs no API key and makes no model calls. |
| Scalability | Evidence is indexed once; cases are independent and run in parallel. |
| Security | API key read from the environment / uncommitted `.env`; never logged or packaged. Evidence text is treated as data, never as instructions. |
| Explainability | Optional per-case trace: identifiers matched, evidence used, rule applied. |
| Portability | Runs on Windows, macOS and Linux with Python 3.11+. Paths resolved from the repository root. |

## 9. Success metrics

Measured by `code/evaluation/` against the 32 sample cases plus our own custom cases:

- Case-level `deletion_status` accuracy
- Step-level and field-level accuracy
- Sequence (ordering) accuracy
- Full run: 518 valid rows, zero schema errors
- Token usage and estimated cost per request

## 10. Deliverables

| Item | Location |
|---|---|
| Runnable solution | `code/` (entry point `code/main.py`) |
| Setup and run guide | `README.md` |
| Evaluation report | `code/evaluation/evaluation_report.md` |
| Usage report | `code/evaluation/usage_report.md` |
| Predictions | `output.csv` (repository root) |
| Chat transcript | `log.txt` (repository root) |

## 11. Risks

| Risk | Mitigation |
|---|---|
| Vision model misreads a screenshot | Strict JSON schema; code checks extracted IDs against known patterns; cached result reviewed once |
| Overfitting to 32 samples | General rules only; extra custom evaluation cases |
| Free-tier rate limits | Batching, retries with backoff, cache |
| Ambiguous evidence citation | Single documented citation rule, validated by the evaluator |
