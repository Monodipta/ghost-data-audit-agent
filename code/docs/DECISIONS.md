# Decisions — Ghost Data Audit Agent

Each entry records the context, the decision, alternatives considered and the consequences. New decisions are appended; superseded ones are marked, not deleted.

---

### D-001 · The model describes, code decides
- **Context:** Most of the task is exact work: identifier matching, timestamp comparison, policy lookup, step ordering. Results are graded field by field.
- **Decision:** Use deterministic code for every decision. Use an LLM only for request intent and for reading screenshots.
- **Alternatives:** An LLM agent that reads evidence and writes steps end to end.
- **Consequences:** Deterministic, cheap, explainable and resistant to prompt injection. Requires writing parsers per format.

### D-002 · Python
- **Context:** No language is mandated. SQLite, PDF and Gemini libraries are mature in Python, and the starter suggests `code/main.py`.
- **Decision:** Python 3.11+ (developed on 3.14).
- **Consequences:** Standard library `sqlite3`, `json`, `csv` cover most parsing.

### D-003 · Google Gemini as the LLM provider
- **Context:** The team has a Gemini API key; no OpenAI or Anthropic key is available.
- **Decision:** Use Gemini via the `google-genai` SDK. `gemini-3.5-flash-lite` for intent; `gemini-3.5-flash` for screenshots. Both are stable releases. Names are configurable in `.env`.
- **Alternatives:** Preview or "latest" aliases (rejected: behaviour can change mid-event); Pro models (rejected: unnecessary cost for these tasks).
- **Consequences:** Provider-specific gateway, isolated behind one module so it can be swapped.

### D-004 · LLM for intent on every request, cached
- **Context:** Requests are multilingual and some resemble deletion while asking for something else.
- **Decision:** Every request text gets a structured Gemini classification, batched about 20 per call and cached by text hash. Code makes the final yes/no from the structured answer.
- **Alternatives:** Keyword rules first with LLM fallback (rejected: rules misfire on paraphrases and other languages).
- **Consequences:** About 26 calls for the full run. A rule-based fallback is kept only for runs without a key or cache.

### D-005 · Vision LLM for screenshots, text extraction for PDFs *(superseded by D-019)*
- **Context:** The 4 PDFs have a real text layer. The 11 PNG screenshots have small console text and no OCR engine is installed.
- **Decision:** PDFs via PyMuPDF text extraction. PNGs via Gemini vision with a strict JSON schema, extracted once and cached.
- **Consequences:** Only 11 vision calls. Extracted resource ids are validated by code before use.

### D-006 · LangGraph for per-case orchestration
- **Context:** Each case passes through several dependent stages with one early exit (non-deletion).
- **Decision:** Stage B is a LangGraph `StateGraph` with a conditional edge after intent. Stage A (index build) stays plain code because it runs once.
- **Alternatives:** Plain function pipeline (simpler, but less explicit and not self-documenting); LangGraph for everything (rejected: Stage A is not a per-case flow).
- **Consequences:** Explicit, visualizable flow; `graph.batch` for parallel cases; a natural place to add agent nodes later.

### D-007 · google-genai SDK directly, not LangChain model wrappers
- **Context:** The usage report needs exact token counts per model; we need our own content-hash cache.
- **Decision:** All model calls go through our gateway using `google-genai`.
- **Consequences:** Full control of caching, retries and metering. LangGraph nodes call the gateway like any function.

### D-008 · Two-stage design: index once, decide per case
- **Context:** 94 evidence files and 518 cases. Re-reading files per case would cost files × cases.
- **Decision:** Parse all evidence once into a shared index; each case is a set of lookups.
- **Consequences:** Cost is files + cases; cases are independent and parallel.

### D-009 · Common Observation record
- **Context:** Six formats and over a dozen layouts express the same facts differently.
- **Decision:** Every parser outputs `Observation(evidence_id, observed_at, system_id, instance, resource_id, category, exists, identifiers, flags)`.
- **Consequences:** Downstream logic is format-agnostic. Adding a format means adding one parser.

### D-010 · Exact identifier matching after normalization
- **Context:** Evidence contains decoys such as `g.silva76@` vs `g.silva76.jr@` and `camille.bernard@` vs `camille.bernard86@`.
- **Decision:** Lowercase and trim; match exactly against the subject's full identifier set. No fuzzy matching.
- **Consequences:** No false links from look-alikes. Historical identifiers from the audit log must be complete.

### D-011 · State is the latest observation at or before audit_at
- **Context:** Records can disappear and reappear; files contain multiple timestamps.
- **Decision:** Use the most specific timestamp (row, then snapshot, then file). The latest observation at or before `audit_at` wins. Later evidence is never used or cited.
- **Consequences:** Correct handling of recreated records and late captures.

### D-012 · Replica ghosts count as present, reported under the base system
- **Context:** Replica tables can keep rows the primary has deleted (sample case_05).
- **Decision:** A resource is present if any instance shows it present at its latest observation. Steps use the base `system_id` (for example `account_service`).
- **Consequences:** Matches the sample output; instance details remain in the trace.

### D-013 · Missing scope is unknown; errors are not absence
- **Context:** Some snapshots omit systems; logs contain timeouts and cache misses.
- **Decision:** Only explicit evidence proves absence: 404 / `rows=0`, `NOT_FOUND`, `profile: null`, or an empty table inside a captured scope.
- **Consequences:** Avoids false `COMPLETE` verdicts.

### D-014 · Claims are cross-checked, never trusted alone
- **Context:** `reported_status` and activity `reported_result` are workflow claims.
- **Decision:** Use activity for identity links, restore events and context. State comes from evidence.
- **Consequences:** Activity events can still be cited when they are the evidence of a data flow or restore.

### D-015 · Evidence citation rule
- **Context:** Several files may show the same resource.
- **Decision:** Cite the evidence that established the resource's state at `audit_at`, i.e. the latest qualifying observation. Validated against the samples by the evaluator.
- **Status:** Provisional until evaluation confirms it.

### D-016 · Evidence text is data
- **Context:** One PDF contains an instruction-like template note.
- **Decision:** Evidence content never alters control flow. Screenshot extraction prompts ask only for structured facts; outputs are schema-validated.
- **Consequences:** Resistant to prompt injection.

### D-017 · Caching and reproducibility
- **Decision:** Cache every LLM response by SHA-256 of model, prompt and input; ship the cache in `code.zip`; temperature 0; sorted iteration and stable JSON serialization.
- **Consequences:** Re-runs are free, offline and byte-identical.

### D-018 · Secrets
- **Decision:** `GEMINI_API_KEY` is read from the environment or an uncommitted `.env`. `.env` is git-ignored and excluded from `code.zip`. The key is never printed or logged. (A standalone `check_setup.py` was used once to confirm model access, then removed as unnecessary.)

### D-019 · One Gemini extraction step for PDFs and screenshots
- **Context:** The 4 PDFs are free-form business documents (statement, support attachment, finance register, compliance journal). Regexes over their text would be brittle and layout-specific.
- **Decision:** PDFs (as PyMuPDF text) and PNGs (as images) both go through the same Gemini extraction prompt and JSON schema. The model only lists visible records (resource id, record type, visible state, identifiers). Code validates resource ids, categories and states before creating observations. Supersedes D-005.
- **Consequences:** 15 cached calls in total. A regex fallback keeps PDFs usable offline without a cache.

### D-020 · Snapshot coverage proves absence
- **Context:** In samples case_01, case_02 and case_04 the account appears only in `system_activity.csv`. The expected answer proves it absent by citing a complete accounts snapshot that does not list it.
- **Decision:** Parsers emit a `Coverage` for every complete listing (SQL table per instance, bundle snapshot, single-collection capture, inventory tables for systems in `snapshot_scope`). A known resource of that system and category that is not listed was absent at that time. Coverages record the snapshot's total row count so empty, suspect captures can be treated differently.
- **Consequences:** Absence can be proven without a record-level "not found" line.

### D-021 · Email hashes of historical emails
- **Context:** Some records are keyed only by `email_hash`. In sample case_12 the hash belongs to the subject's old email.
- **Decision:** Email hash is `sha256(lowercase(email))`, verified for all 850 identities. Identity resolution adds the hash of every current and historical email.

### D-022 · Hash-keyed contact-index records are SECONDARY_IDENTIFIER
- **Context:** `contact_lookup` / `contact_query` / `deletion_marker_check` log events describe contact-index entries (keyed by email or email hash) inside analytics and support systems. Samples case_10 and case_12 expect them deleted, not anonymized or redacted.
- **Decision:** Map these events to `SECONDARY_IDENTIFIER` (policy: DELETE).

### D-023 · Offline mode never reads secrets
- **Decision:** `--offline` skips loading `.env` and never touches `GEMINI_API_KEY`; it uses cached answers only. Online runs load `.env`.
- **Consequences:** Reviewers (and sandboxed tools) can run the full pipeline from the shipped cache without any key.
### D-024 · Evaluation lives in code/evaluation/, with everything written into Markdown
- **Context:** The README places `evaluation_report.md` and `usage_report.md` in `code/evaluation/` (beside the starter's `code/evaluation/main.py`) and notes that the automated code judge ignores raw data files (.csv, .json, .jsonl, .sql, .log).
- **Decision:** `code/evaluation/main.py` is the evaluation entry point. Custom evaluation cases are defined in Python (`custom_cases.py`), and every metric, custom case and token/cost table is written directly into the two Markdown reports. Prompts stay in Python source.
- **Consequences:** The judge and the AI interviewer can see all evaluation content. The JSON cache is still shipped for reproducibility but is not relied on for anything the judge must read.
### D-025 · Rate limiting and retry policy for the free tier
- **Context:** The first online run hit Gemini free-tier limits (5 requests per minute per model, 429) and temporary 503 "high demand" errors, because four worker threads sent requests in bursts.
- **Decision:** The gateway has a per-model rolling-minute rate limiter shared across threads (`LLM_RPM`, default 4). Retries go up to 6 attempts; on a 429 the gateway waits for the server's suggested `retry in Ns` delay, otherwise it uses exponential backoff (5 s doubling, capped at 90 s).
- **Consequences:** Slower first run (about 4 minutes for 15 documents), no failures; cached runs are unaffected.

### D-026 · Document extraction schema: separate presence, identifiers and process state
- **Context:** A single `state` enum forced the model to choose between "shows PII" and "can be restored" for a backup screenshot, losing the restore risk. A delivery-correction PDF that is itself a ticket attachment was labelled as a support message.
- **Decision:** The schema now has three independent fields: `presence` (PRESENT/ABSENT), `shows_personal_identifiers` (bool) and `process_state` (ACTIVE/INACTIVE/NOT_APPLICABLE, used only for data flows and backups). The prompt states that an artifact that is itself an uploaded attachment is `SUPPORT_ATTACHMENT`, and that staff or agent identifiers must not be listed.
- **Consequences:** The prompt change invalidates the earlier cache; all 15 documents are re-extracted once.

### D-027 · Names never link a record on their own
- **Context:** A support screenshot lists an agent's name next to the customer's. Names also collide across people.
- **Decision:** Records are linked to a subject by email, phone, email hash or user id. A name match only corroborates a link that a strong identifier already supports.
### D-028 · Fail fast on daily quotas and fall back to another model
- **Context:** The second online run produced no output for over 10 minutes. After 3 successful extractions, every call returned 429 for the free-tier *daily* quota, and the gateway kept retrying a limit that would not reset that day, without printing anything.
- **Decision:** A 429 whose quota id is per-day is not retried. The model is marked exhausted for the run and the next model in a fallback chain is tried (documents: `gemini-3.5-flash` → `gemini-3.7-flash` → `gemini-2.5-flash`; intent: `gemini-3.5-flash-lite` → `gemini-3.1-flash-lite` → `gemini-2.5-flash-lite`). Each Gemini model has its own free quota. Every document now logs a progress line. If every model is exhausted, the deterministic fallback is used and a warning names the file.
- **Consequences:** A first run can finish on the free tier. Different documents may be extracted by different models; the cache records which, and the usage report lists them per model.
### D-029 · Unknown layouts fall back to model extraction
- **Context:** The parsers were written for the layouts in this dataset. A new evidence file with a different layout or file type would previously have been skipped with a warning, silently losing its facts.
- **Decision:** If a text file yields no observations and no coverage from the deterministic parsers, it is sent through the same Gemini extraction prompt and schema as PDFs (truncated to 60,000 characters), and the output is validated by code. Without a model it falls back to the regex reading. Unknown binary types are skipped with a warning.
- **Consequences:** The pipeline degrades gracefully on new evidence. No current file triggers the fallback, so it adds no calls to this dataset's run.

### D-030 · Standard-library unit tests, including a no-hardcoded-labels guard
- **Decision:** Tests use `unittest` (no extra dependency; pytest also runs them). Inputs are synthetic. One test fails if any case, evidence, activity or audit id appears in the solution code.
### D-031 · Citation rule R3
- **Context:** Several files often describe the same resource. Some exports contain rows timestamped before `audit_at` but were captured after it.
- **Decision:** Cite the latest explicit observation whose row time and file capture time are both ≤ `audit_at`; within one snapshot a record present in any instance (primary or replica) is present. With no explicit observation, the latest non-empty complete snapshot decides (not listed → absent).
- **Evidence:** Reproduces all 75 evidence ids cited in the public samples; a rule using row time only reproduces 39.

### D-032 · Late exports: known, never cited, never a finding
- **Context:** Retained security-audit records appear only in exports captured days after `audit_at`, in rows dated at `audit_at`. The sample plans still include their future checks.
- **Decision:** A row dated ≤ `audit_at` inside a later export makes the record *known* (`known_late`). It may link a record and support a non-violation future check (VERIFY_RECORD_PRESENT for a retained record, VERIFY_RECORD_ABSENT for an already-deleted one) in an INCOMPLETE case, but it is never cited and never produces a finding or a COMPLETE verification. A listing beats a coverage omission at the same timestamp.
- **Consequences:** Step F1 on the samples 80.8% → 93.0%; no answer depends on evidence that did not exist at audit time.

### D-033 · Workflow-activity linking with global assignment (user decision)
- **Context:** About 25% of expected resources (already-deleted accounts, already-anonymized analytics) carry no identifiers anywhere; only the deletion workflow's events name them, within about −1.25 h to +2 h of `reported_at`. Many cases share the same `reported_at`.
- **Decision:** Candidate events in that window are assigned across all known requests at once: identifier links win; score = time distance minus a 30-minute bonus when audit-time evidence inspected the resource; one resource per category per case; never a resource whose evidence ties it to another person. Window and bonus are named constants in `linking.py`.
- **Alternatives:** Identifier-only linking (no false links, but misses most account verification steps). The `user_0N → account_00N` naming seen in some samples was rejected as a hardcoded shortcut.
- **Consequences:** Most workflow-only resources are found. When cases are processed in one batch the workflow logs each event type in resource-id order, so a few assignments are inherently ambiguous; this is reported, not hidden.

### D-034 · Verify every linked record in INCOMPLETE cases (user decision)
- **Decision:** Already-compliant records also get their verification step in INCOMPLETE plans, consistent with COMPLETE cases and with "the checks that must pass afterward".

### D-035 · Earlier requests by the same person bound the evidence
- **Context:** One person filed two requests months apart; the older request's lookups (for example a 404 months earlier) do not belong to the newer case.
- **Decision:** If another request by the same person was audited before this request was made, identifier evidence dated at or before that audit is ignored for this case.

### D-036 · Named-object pass for documents without record ids
- **Context:** A storage-browser screenshot shows an attachment only by file name; the activity catalog names the resource with that file name in parentheses.
- **Decision:** When a document yields no record ids, a second Gemini pass lists named stored objects; code resolves names through catalog aliases and drops names nobody catalogued.
- **Consequences:** 4 extra cached calls; recovers an attachment that would otherwise be invisible.

### D-037 · Output ordering and serialization
- **Decision:** Rows are written in numeric case order (matching `deletion_requests.csv`), steps as compact JSON with the field order of the spec, UTF-8, LF line endings. Every row passes `validate.py` before writing.

### D-038 · Usage report counts every model answer the run used
- **Decision:** A cached answer still cost tokens once, so the usage report counts live and cached answers with their original token counts and estimates cost at paid list prices (actual free-tier cost $0). Every full `run` rewrites it.

### D-039 · Unavoidable misses are documented, not faked
- **Context:** Three expected resources in the samples appear in no evidence file and no activity row.
- **Decision:** No guessing of ids. The evaluation report classifies each remaining miss as "not in any data" or "linking".

### D-040 · Packaging and a reproducible, minimal cache
- **Decision:** `code.zip` holds the root `README.md` and `code/` (sources, docs, tests, both evaluation reports, and the Gemini answer cache), and excludes `.env`, `dataset/`, `__pycache__`, traces and archives. The gateway records which cache files a run uses; cache entries left over from earlier prompt versions were pruned (53 → 41 files).
- **Verification:** the zip was extracted into an empty folder with `dataset/` beside it; an offline run made 0 model calls and produced an `output.csv` byte-identical to the submitted one, and all 34 tests passed. A scan of every zipped file found no key-like strings.
