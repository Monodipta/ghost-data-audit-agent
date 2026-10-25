# Token Usage and Cost Report

Final full-dataset run that produced `output.csv`: 518 requests from `dataset/deletion_requests.csv`, generated 2026-10-25 14:46 UTC (offline, every model answer served from the cache).

**Provider:** Google Gemini API (`google-genai` SDK), temperature 0, JSON response schema.

## Per-model totals

| Model | Used for | Model answers used | Live calls this run | Input tokens | Output tokens (incl. thinking) | Total tokens | Estimated cost (USD) |
|---|---|---|---|---|---|---|---|
| gemini-3.5-flash | documents, documents_files | 4 | 0 | 5,233 | 6,329 | 11,562 | $0.0648 |
| gemini-3.5-flash-lite | intent | 19 | 0 | 20,118 | 15,030 | 35,148 | $0.0436 |
| gemini-3.7-flash | documents, documents_files | 15 | 0 | 19,262 | 22,395 | 41,657 | $0.0984 |
| **Overall** | | **38** | **0** | **44,613** | **43,754** | **88,367** | **$0.2068** |

## Per request

| Measure | Value |
|---|---|
| Requests | 518 |
| Model answers per request | 0.073 |
| Input tokens per request | 86.1 |
| Output tokens per request | 84.5 |
| Total tokens per request | 170.6 |
| Estimated cost per request (USD) | $0.000399 |
| Estimated total cost (USD) | $0.2068 |
| Actual cost (Gemini free tier) | $0.00 |

## Why usage is this low

- The model is used only where language or vision is needed: request intent (distinct texts, about 20 per call) and documents without a fixed layout (PDFs and screenshots, one call each, plus a named-object pass for documents with no record ids). Every SQL, JSON, log and text file is parsed by code.
- Every answer is cached by a hash of model, prompt, schema and input, so re-runs cost nothing and give byte-identical output.
- Document extraction is shared by all cases: its cost does not grow with the number of requests.

## Price sources

- gemini-3.5-flash-lite $0.30 / $2.50 and gemini-3.5-flash $1.50 / $9.00: third-party price trackers citing the Gemini API pricing page (Aug-Sep 2026).
- gemini-3.7-flash $0.75 / $3.75: Google Cloud introductory price through 2026-12-31 (standard $1.50 / $7.50 from 2027).
- gemini-2.5-flash $0.30 / $2.50 and gemini-2.5-flash-lite $0.10 / $0.40: Gemini API list prices at their 2025 release. gemini-3.1-flash-lite has no verified price and is shown as 'not priced'. Fallback models are only used when a preferred model's daily free quota is exhausted.
