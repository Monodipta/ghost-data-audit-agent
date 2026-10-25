# Evaluation Report

Generated 2026-10-25 05:23 UTC by `python code/evaluation/main.py --offline --write-report`.
Mode: offline (cached model answers only). Intent decided by: model 32.

## 1. Results

| Metric | Public samples (32) | Custom cases |
|---|---|---|
| Case-level status accuracy | 100.0% | 100.0% |
| Step precision | 94.3% | 100.0% |
| Step recall | 93.8% | 100.0% |
| Step F1 | 94.0% | 100.0% |
| Cases with exactly the right step set | 62.5% | 100.0% |
| Sequence accuracy (exact ordered steps) | 62.5% | 100.0% |
| Mean sequence similarity (LCS ratio) | 91.6% | 100.0% |
| Steps TP / FP / FN | 181 / 11 / 12 | 5 / 0 / 0 |

### Field-level accuracy (public samples)

Positional: step *i* of our list is compared with step *i* of the expected list, field by field (missing or extra steps count as wrong, so this is also sensitive to order).

| Field | Positional accuracy |
|---|---|
| `phase` | 97.4% |
| `system_id` | 93.3% |
| `resource_id` | 89.2% |
| `operation` | 93.3% |
| `state` | 93.3% |
| `evidence_id` | 96.9% |
| `step_no` | 97.4% |

**Citation accuracy:** of the 181 expected steps we also produced (same phase, system, resource and operation), 181 cite exactly the expected `evidence_id` (100.0%), including the empty id required for future remediation and checks.

## 2. How we evaluate

- **Status accuracy:** predicted `deletion_status` equals the expected one.
- **Step-level:** a step matches only if phase, system_id, resource_id, operation, state and evidence_id are all equal (step_no ignored). Micro precision, recall and F1 over all steps.
- **Sequence accuracy:** the full ordered step list, including step numbers, is identical. The LCS ratio gives partial credit for order.
- The expected answers come only from `dataset/sample_output.csv` (public) and from our own custom cases below. They are used for scoring only and never by the pipeline.

## 3. Per-case results (public samples)

| Case | Expected | Predicted | TP | FP | FN | Exact sequence | LCS |
|---|---|---|---|---|---|---|---|
| case_01 | COMPLETE | COMPLETE | 1 | 0 | 0 | yes | 100% |
| case_02 | COMPLETE | COMPLETE | 1 | 0 | 0 | yes | 100% |
| case_03 | COMPLETE | COMPLETE | 2 | 1 | 1 | no | 67% |
| case_04 | COMPLETE | COMPLETE | 1 | 0 | 1 | no | 50% |
| case_05 | INCOMPLETE | INCOMPLETE | 3 | 0 | 0 | yes | 100% |
| case_06 | INCOMPLETE | INCOMPLETE | 4 | 0 | 0 | yes | 100% |
| case_07 | INCOMPLETE | INCOMPLETE | 4 | 0 | 0 | yes | 100% |
| case_08 | INCOMPLETE | INCOMPLETE | 4 | 0 | 0 | yes | 100% |
| case_09 | INCOMPLETE | INCOMPLETE | 5 | 1 | 0 | no | 83% |
| case_10 | INCOMPLETE | INCOMPLETE | 4 | 0 | 0 | yes | 100% |
| case_11 | INCOMPLETE | INCOMPLETE | 14 | 0 | 0 | yes | 100% |
| case_12 | INCOMPLETE | INCOMPLETE | 5 | 0 | 0 | yes | 100% |
| case_13 | INCOMPLETE | INCOMPLETE | 8 | 0 | 0 | yes | 100% |
| case_14 | INCOMPLETE | INCOMPLETE | 5 | 0 | 0 | yes | 100% |
| case_15 | INCOMPLETE | INCOMPLETE | 5 | 0 | 0 | yes | 100% |
| case_16 | INCOMPLETE | INCOMPLETE | 7 | 0 | 0 | yes | 100% |
| case_17 | INCOMPLETE | INCOMPLETE | 5 | 0 | 0 | yes | 100% |
| case_18 | INCOMPLETE | INCOMPLETE | 12 | 1 | 2 | no | 86% |
| case_19 | INCOMPLETE | INCOMPLETE | 8 | 0 | 0 | yes | 100% |
| case_20 | INCOMPLETE | INCOMPLETE | 6 | 2 | 2 | no | 75% |
| case_21 | COMPLETE | COMPLETE | 3 | 0 | 0 | yes | 100% |
| case_22 | INCOMPLETE | INCOMPLETE | 8 | 0 | 0 | yes | 100% |
| case_23 | INCOMPLETE | INCOMPLETE | 7 | 1 | 1 | no | 88% |
| case_24 | INCOMPLETE | INCOMPLETE | 7 | 1 | 0 | no | 88% |
| case_25 | COMPLETE | COMPLETE | 3 | 0 | 0 | yes | 100% |
| case_26 | COMPLETE | COMPLETE | 5 | 0 | 1 | no | 83% |
| case_27 | COMPLETE | COMPLETE | 5 | 1 | 1 | no | 83% |
| case_28 | COMPLETE | COMPLETE | 5 | 1 | 1 | no | 83% |
| case_29 | INCOMPLETE | INCOMPLETE | 14 | 0 | 0 | yes | 100% |
| case_30 | INCOMPLETE | INCOMPLETE | 14 | 0 | 0 | yes | 100% |
| case_31 | COMPLETE | COMPLETE | 2 | 1 | 1 | no | 67% |
| case_32 | INCOMPLETE | INCOMPLETE | 4 | 1 | 1 | no | 80% |

## 4. Custom evaluation cases

Created by the team to test behaviours the public samples do not cover. Expected answers were derived by hand from the dataset and the problem statement.

### custom_01: Negated deletion in English — PASS

- **Request:** email `novak.tomasz@icloud.com`, requested 2026-09-09T12:00:00Z, reported NOT_STARTED at 2026-09-12T12:00:00Z, audit_at 2026-10-01T12:00:00Z
- **Text:** "Please send me a copy of all the data you hold about me. Do not delete or change anything; I want to keep using my account."
- **Why:** The text asks for a data copy and explicitly says not to delete. The subject has a real account with remaining data, so a keyword or evidence-driven shortcut would wrongly audit it.
- **Expected:** NOT_APPLICABLE, 0 steps
- **Predicted:** NOT_APPLICABLE, 0 steps

### custom_02: Non-deletion request in Spanish — PASS

- **Request:** email `amina.elmasri@gmail.com`, requested 2026-08-18T09:14:00Z, reported NOT_STARTED at 2026-08-20T16:42:00Z, audit_at 2026-09-03T11:30:00Z
- **Text:** "Quisiera recibir una copia de mis datos personales. Por favor, no borren nada de mi cuenta."
- **Why:** 'I would like a copy of my personal data. Please do not erase anything from my account.' This is an access request in another language with a negated deletion verb.
- **Expected:** NOT_APPLICABLE, 0 steps
- **Predicted:** NOT_APPLICABLE, 0 steps

### custom_03: Historical email, written in upper case — PASS

- **Request:** email `NADIA.IONESCU@YAHOO.COM`, requested 2026-08-31T15:42:00Z, reported COMPLETE at 2026-09-02T10:08:00Z, audit_at 2026-09-18T12:25:00Z (stands in for case_10)
- **Text:** "I used this Yahoo address before changing the email on my account. Please remove records linked to both the old and current addresses."
- **Why:** Same subject and dates as sample case_10, but the request email is the oldest address in a three-step email chain and is upper-cased. Identity must be resolved case-insensitively through the audit log; the answer must equal the published case_10 answer.
- **Expected:** INCOMPLETE, 4 steps
  - 1. FINDING REPORT_REMAINING_RECORD support_platform/support_002 PRESENT evidence=`evidence_61`
  - 2. REMEDIATION DELETE_RECORD support_platform/support_002 ABSENT evidence=``
  - 3. VERIFICATION VERIFY_RECORD_ABSENT account_service/account_010 ABSENT evidence=``
  - 4. VERIFICATION VERIFY_RECORD_ABSENT support_platform/support_002 ABSENT evidence=``
- **Predicted:** INCOMPLETE, 4 steps

### custom_04: Evidence after audit_at must be ignored — PASS

- **Request:** email `leila.haddad@yahoo.com`, requested 2026-08-27T14:17:00Z, reported COMPLETE at 2026-08-28T09:03:00Z, audit_at 2026-09-02T22:00:00Z (stands in for case_05)
- **Text:** "I deleted this account and received a confirmation, but the same email address is still recognized. Please remove any remaining copy of my profile."
- **Why:** Sample case_05 is INCOMPLETE because the failover replica captured at 2026-09-02T23:00 (evidence_54) still holds the profile. Moving audit_at to 22:00 the same day hides that capture. The latest complete account snapshot before then (evidence_10, 2026-08-27, primary and read replica) does not list the profile, so at that time the deletion is proven complete.
- **Expected:** COMPLETE, 1 steps
  - 1. VERIFICATION VERIFY_RECORD_ABSENT account_service/account_005 ABSENT evidence=`evidence_10`
- **Predicted:** COMPLETE, 1 steps

## 5. Remaining failures (public samples)

| Case | Missing step | Cause |
|---|---|---|
| case_03 | VERIFY_RECORD_ANONYMIZED analytics_platform/analytics_9406 | linking |
| case_04 | VERIFY_RECORD_ABSENT account_service/account_004 | not in any data |
| case_18 | VERIFY_RECORD_ABSENT account_service/account_5521 | linking |
| case_18 | VERIFY_RECORD_PRESENT security_service/audit_record_6645 | not in any data |
| case_20 | VERIFY_RECORD_ABSENT account_service/account_5037 | linking |
| case_20 | VERIFY_RECORD_PRESENT security_service/audit_record_5569 | not in any data |
| case_23 | VERIFY_RECORD_ABSENT account_service/account_410 | linking |
| case_26 | VERIFY_RECORD_ANONYMIZED analytics_platform/analytics_4566 | linking |
| case_27 | VERIFY_RECORD_ANONYMIZED analytics_platform/analytics_4574 | linking |
| case_28 | VERIFY_RECORD_ANONYMIZED analytics_platform/analytics_6077 | linking |
| case_31 | VERIFY_RECORD_ABSENT account_service/account_4857 | linking |
| case_32 | VERIFY_RECORD_ABSENT account_service/account_8858 | linking |

- **Not in any data (3 steps):** the expected resource id appears in no evidence file and no activity row, so no evidence-based system can find it. We do not guess ids.
- **Linking (9 steps):** resources with no identifiers anywhere (deleted accounts, anonymized analytics) are known only from the deletion workflow's activity. When several cases share the same reported_at, the workflow processes them as one batch and logs each event type in resource-id order, so some assignments are indistinguishable. Extra steps in the same cases are the mirror image of these.

## 6. Failures found and improvements made

| Area | Failure found | Change | Measured effect |
|---|---|---|---|
| Stage A | Pipe-delimited logs produced 0 records (off-by-one in the field split). | Fixed the split; a per-file 'produced no facts' check now runs after every index build. | 2 log files recovered (+77 observations). |
| Stage A | A backup screenshot lost its 'can still be restored' fact: one `state` enum forced the model to choose between 'shows PII' and 'restorable'. | Split the extraction schema into presence, shows_personal_identifiers and process_state. | Restore risk now extracted; all 25 document records verified against the source files. |
| Stage A | A delivery-correction PDF that is itself a ticket attachment was labelled a support message, and an agent's name was captured as a customer identifier. | Prompt states that an artifact which is an uploaded file is SUPPORT_ATTACHMENT and excludes staff. | Correct DELETE treatment for the attachment; no staff names linked. |
| Stage A | The free tier returned per-minute and per-day quota errors; a run sat silent for 10+ minutes. | Per-model rate limiter, server-suggested retry delays, fail-fast on daily quota with a model fallback chain, and a progress line per document. | All 15 documents extracted in one run (failover to gemini-3.7-flash). |
| Baseline | First end-to-end run on the samples. | - | Status 78.1%, step F1 80.8%, exact sequence 37.5%. |
| Intent | Offline rule fallback missed paraphrases ('I'm deleting my account', 'the profile is gone', 'remove records under both addresses'), so 7 deletion requests became NOT_APPLICABLE. | Broader multilingual stems for delete / erase / remove / close plus explicit negation patterns. | Status accuracy 78.1% -> 100%. |
| State | Retained security-audit records were missing from INCOMPLETE plans: their only rows are timestamped at audit_at inside exports captured days later. | Rows dated <= audit_at may link a record and support a future check, but are never cited and never produce a finding. | Step F1 80.8% -> 91.3%. |
| State | A coverage at the same instant omitted a record that another export listed; deleted accounts known only from late exports were dropped. | A listing beats an omission at the same timestamp; late-known compliant records get future checks. | Step F1 91.3% -> 93.0%. |
| Linking | Workflow-only accounts were matched to the wrong case when several cases share reported_at. | Score candidates by distance to reported_at with a 30-minute bonus for resources that audit-time evidence inspected (e.g. a 404 readback). | Step F1 93.0% -> 94.0%, exact sequence 62.5%. |
| Linking | An attachment visible only by file name in a storage-browser screenshot could not be linked. | Second extraction pass lists named objects when a document has no record ids; the activity catalog's alias (resource id -> file name) resolves them. | Recovers the attachment for the affected request in the full dataset. |

Guard rails that keep these results honest: the expected answers are never read by the pipeline, a unit test fails if any case, evidence, activity or audit id appears in the solution code, and tuning stopped once the remaining errors were either impossible (no data) or symmetric ties, to avoid overfitting to 32 cases.

## 7. Model usage during this evaluation run

| Model | Live calls | Cached calls | Input tokens | Output tokens |
|---|---|---|---|---|
| gemini-3.5-flash | 0 | 4 | 5233 | 597 |
| gemini-3.5-flash-lite | 0 | 3 | 2076 | 1485 |
| gemini-3.7-flash | 0 | 15 | 19262 | 2514 |
