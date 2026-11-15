# Architecture

```
Streamlit UI ──HTTP (Bearer)──▶ FastAPI ──▶ LangGraph workflows ──▶ tools ──▶ GitHub REST API
                                   │              │                          (allowlisted client)
                                   │              └──▶ Groq (JSON mode)
                                   └──▶ PostgreSQL  (data, sessions, approvals, ledger, rate limits, job queue)
Worker (python -m app.workers.queue) ──▶ PostgreSQL job queue (FOR UPDATE SKIP LOCKED) ──▶ evaluation / repository jobs
```

* **No Redis.** Rate limits (`rate_limit_counters`), idempotency (`github_actions`), OAuth state (`oauth_states`) and
  jobs (`background_jobs`) live in PostgreSQL.
* **Layers.** `api/routes` → `workflows` (LangGraph graphs: repository_inspection, code_review, issue_proposal,
  comment_generation, logging_generation, publishing) → `agents` (LLM prompts + deterministic `patch_agent`) →
  `tools` (read / write / analysis) → `integrations/github` (client, one module per endpoint family).
* **Read vs write separation.** `ToolContext` refuses a write-capable client; `WriteToolContext` requires one. Write
  tools are only reachable from the publishing workflow, which runs only for an approval in `PUBLISHING`.
* **Frontend.** Streamlit keeps API tokens in server-side session state; the browser never receives them.
* **Models.** Groq only; the model name is configuration (`GROQ_MODEL`), and evaluation runs can override it.
