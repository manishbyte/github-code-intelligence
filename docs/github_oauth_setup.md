# GitHub OAuth setup

1. GitHub → Settings → Developer settings → **OAuth Apps** → *New OAuth App*.
2. **Authorization callback URL** = `GITHUB_CALLBACK_URL` (local: `http://localhost:8000/api/v1/github/oauth/callback`).
   GitHub allows one callback URL per OAuth app: create a separate app for production.
3. Put the Client ID in `GITHUB_CLIENT_ID` and a generated Client Secret in `GITHUB_CLIENT_SECRET` (server-side only).
4. Generate `GITHUB_TOKEN_ENCRYPTION_KEY` (Fernet; comma-separate several keys to rotate):
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

**Scopes.** Read-only connection requests no scope (public data). "Write access" requests `public_repo` only, and only
when the user asks for it. Private repositories are not supported.

**Flow.** The Streamlit app calls `/github/oauth/start` and shows a link that opens GitHub in a new tab. After
authorizing, GitHub redirects to the backend callback, which consumes the single-use `state` (bound to the user who
started the flow), exchanges the code, stores the encrypted token and shows a static confirmation page. Press *Refresh
status* in the app. Disconnecting revokes the grant at GitHub and deletes the stored token.
