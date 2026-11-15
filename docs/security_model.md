# Security model

**Authentication.** scrypt password hashing; HS256 access tokens (15 min) bound to a server-side session; opaque
refresh tokens stored as SHA-256 hashes with rotation and reuse detection. Cookies are HttpOnly/SameSite=Lax (Secure in
production); cookie-authenticated unsafe requests must carry an allowed `Origin`.

**Isolation.** Every query is scoped by `user_id`; cross-user access returns 404 (`core/permissions.ensure_owner`).
Roles: `user`, `recruiter` (read evaluation dashboards), `admin`.

**Untrusted input.** Repository text is fenced with a random boundary, scanned for injection patterns, and secrets are
redacted before any model call. Model output must parse into strict schemas; findings are accepted only if their line
range and verbatim evidence exist in the file. Issue bodies are assembled by code from validated data and displayed as
plain text. Paths are validated (no traversal, `.git`, protected `.github/workflows/`).

**Patch safety.** The model proposes insertions only. Deterministic validators check language-specific comment/log
syntax, forbid sensitive identifiers, then apply and diff them. Unified diffs are parsed strictly (single file, no
renames/modes/binaries, exact context, no fuzz), re-scanned for secrets and syntax-checked where a checker exists.
Repository code is never executed.

**GitHub writes.** Allowlisted endpoints only; read-only client by default; branches must be under `code-intel/`;
no merges, deletes or force pushes exist. Each write requires an `ApprovedAction` created only from a request in
`PUBLISHING`, bound to user, repository, action type, payload digest and expiry, plus a PostgreSQL idempotency ledger
and a permission check. Results are verified by reading GitHub back; unverifiable results are never reported as success.

**Secrets.** GitHub tokens are Fernet-encrypted at rest; logs and audit details are redacted; startup validation fails
fast in production on missing/weak settings.

**Known limits.** A publish interrupted by a process crash leaves the approval in `PUBLISHING` and ledger rows in
`in_progress`/`unknown`; re-run `publish` is blocked until reconciled (commit and PR steps self-reconcile after 10 minutes,
issue creation never auto-retries to avoid duplicates).
