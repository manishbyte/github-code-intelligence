import streamlit as st

from components.layout import page_header, show_error
from lib import api_client as api
from lib import auth
from lib.formatting import fmt_dt

auth.require_login()
page_header("GitHub connection", "Your GitHub token is encrypted at rest and never shown in this app.")


def _account():
    try:
        return api.get("/github/account")
    except api.ApiError as exc:
        show_error(exc)
        st.stop()


account = _account()
if account:
    c1, c2 = st.columns([1, 4])
    if account.get("avatar_url"):
        c1.image(account["avatar_url"], width=72)
    c2.markdown(f"**@{account['login']}** · connected {fmt_dt(account['connected_at'])}")
    c2.write("Access: " + ("**read and write** (public repositories)" if account["can_write"] else "**read-only**"))
    c2.caption("Granted scopes: " + (", ".join(account["granted_scopes"] or []) or "none (public data only)"))
else:
    st.info("No GitHub account connected.")

st.divider()
st.subheader("Connect or change access")
st.write(
    "Authorization opens in a **new tab** on github.com. When it says *Connected*, close that tab and press "
    "**Refresh status** here."
)
c1, c2 = st.columns(2)
for col, access, label, hint in (
    (c1, "read", "Connect (read-only)", "Inspect and review public repositories."),
    (c2, "write", "Connect with write access", "Also allows creating issues, branches, commits and pull requests after you approve them (`public_repo` scope)."),
):
    with col:
        st.caption(hint)
        if st.button(label, key=f"start-{access}", use_container_width=True):
            try:
                st.session_state[f"oauth-{access}"] = api.get("/github/oauth/start", params={"access": access})["authorization_url"]
            except api.ApiError as exc:
                show_error(exc)
        if st.session_state.get(f"oauth-{access}"):
            st.link_button("Continue on GitHub ↗", st.session_state[f"oauth-{access}"], use_container_width=True)

if st.button("🔄 Refresh status"):
    st.rerun()

if account:
    st.divider()
    with st.expander("Disconnect"):
        st.write("This revokes this app's access on GitHub and deletes the stored token.")
        if st.button("Disconnect GitHub", type="secondary"):
            try:
                api.delete("/github/account")
                st.rerun()
            except api.ApiError as exc:
                show_error(exc)
