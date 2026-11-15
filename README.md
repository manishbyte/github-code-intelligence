# GitHub Code Intelligence

Inspect public GitHub repositories, review code with an LLM (Groq), and — **only after you approve** — publish
issues, comments or logging changes back to GitHub. Backend: FastAPI + PostgreSQL + LangGraph. Frontend: Streamlit.

## Quick start (Docker)

```bash
cp .env.example .env
# fill in: APP_SECRET_KEY, POSTGRES_PASSWORD, GITHUB_CLIENT_ID/SECRET, GITHUB_TOKEN_ENCRYPTION_KEY, GROQ_API_KEY, GROQ_MODEL
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # -> GITHUB_TOKEN_ENCRYPTION_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"                                # -> APP_SECRET_KEY
docker compose up --build
```

* App: http://localhost:8501 · API docs: http://localhost:8000/docs
* Create the GitHub OAuth app first: see `docs/github_oauth_setup.md`.
* Make yourself an administrator (needed to start evaluation runs):
  `docker compose exec postgres psql -U gci -d github_intelligence -c "UPDATE users SET role='admin' WHERE email='you@example.com';"`
  (use role `recruiter` for read-only access to the evaluation dashboards).

## Run without Docker

```bash
cd backend && pip install -r requirements.txt
export $(grep -v '^#' ../.env | xargs) && alembic upgrade head
uvicorn app.main:app --reload            # API
python -m app.workers.queue              # background worker (evaluation runs)
cd ../frontend && pip install -r requirements.txt && API_BASE_URL=http://localhost:8000 streamlit run app.py
```

## Layout

`backend/` API, workflows, agents, guardrails, approvals, evaluation, worker · `frontend/` Streamlit app ·
`evaluation_data/` labelled evaluation cases · `infrastructure/` production compose · `docs/` design documents.

## Safety in one paragraph

Repository content is untrusted data (fenced, scanned for injection, secrets redacted before any model sees it).
The model never writes code that reaches GitHub: it proposes insertions that deterministic validators apply and diff.
GitHub writes require an explicit human approval bound to the exact content (digest), run through an
`APPROVED → PUBLISHING → PUBLISHED` state machine, are idempotent, permission-checked, and verified by re-reading GitHub.
See `docs/security_model.md`.
