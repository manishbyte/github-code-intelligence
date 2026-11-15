# Evaluation methodology

Datasets live in `evaluation_data/<suite>/*.json` (`{"cases":[{"key","input","expected"}]}`) and are synced into
PostgreSQL by content hash. Suites:

| Suite | Directory | Type | What is measured |
|---|---|---|---|
| tree | `repository_trees` | deterministic | tree normalization, unsafe-path skipping |
| patch | `patch_validation` | deterministic | patch parser/applier accepts good and rejects unsafe diffs |
| safety | `security` | deterministic | injection, secret, path, URL and branch guardrails |
| issue | `issue_decisions` | deterministic | duplicate detection, issue-body assembly |
| review | `code_review` | LLM | decision correctness, finding recall/precision, validation rejections |
| comment / logging | `comment_generation`, `logging_generation` | LLM | patch built, safe, syntax-valid, only insertions, min edits, no sensitive logging |

An optional LLM judge adds a 1–5 quality score (never used for safety). Cases that cannot be scored (e.g. model
unavailable) are counted as **errors**, not passes or failures. Each run stores per-case results, aggregate pass rate,
mean score and p50/p95 latency, and is compared to the previous run with the same suite and model: any drop over 5
points (0 for `safety` and `patch`) is flagged as a regression. Runs are started by an administrator and executed by the worker.
