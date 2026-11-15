# API contracts (prefix `/api/v1`)

Errors: `{"error": {"code", "message", "request_id"}}`. Auth: `Authorization: Bearer <access token>` or cookies set by `/auth/login`.

| Area | Endpoint | Notes |
|---|---|---|
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` | refresh tokens rotate; reuse revokes all sessions |
| Users | `GET/PATCH /users/me` | |
| GitHub | `GET /github/oauth/start?access=read\|write`, `GET /github/oauth/callback`, `GET/DELETE /github/account`, `GET /github/repositories`, `GET /github/repositories/{id}/permissions` | callback identifies the user by the single-use `state` |
| Repositories | `POST /repositories/inspect`, `GET /repositories/{id}`, `GET /repositories/{id}/tree`, `POST /repositories/{id}/refresh`, `GET /repositories/{id}/files/{path}` | public repos only; pinned to commit SHA |
| Reviews | `POST /reviews`, `GET /reviews/{id}`, `GET /reviews/{id}/findings` | |
| Issues | `POST /reviews/{id}/issue-proposals`, `GET /issue-proposals/{id}` | creates a `create_issue` approval |
| Code changes | `POST /code-changes/comments`, `POST /code-changes/logging`, `GET /code-changes/{id}`, `GET /code-changes/{id}/diff` | creates a `publish_code_change` approval |
| Approvals | `GET /approvals`, `GET /approvals/{id}`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/reject`, `POST /approvals/{id}/publish` | decision body: `{"displayed_payload_digest": "<sha256>"}` |
| Actions | `GET /github-actions/{id}` | |
| History | `GET /history?kind=&limit=&offset=` | |
| Evaluation | `POST /evaluations/runs` (admin), `GET /evaluations/runs`, `/runs/{id}`, `/runs/{id}/metrics`, `/runs/{id}/cases`, `/overview`, `/comparison`, `/reports/{id}/export?format=csv\|md\|json` | admin / recruiter roles |
| Ops | `GET /health`, `GET /health/ready`, `GET /metrics` (admin) | |
