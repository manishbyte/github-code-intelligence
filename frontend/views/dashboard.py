import streamlit as st

from components.layout import page_header, show_error
from components.recruiter import metric_row
from lib import api_client as api
from lib import auth
from lib.formatting import fmt_dt

user = auth.require_login()
page_header(f"Welcome, {user['display_name']}", "Inspect public repositories, review code, and publish changes only after you approve them.")
try:
    account = api.get("/github/account")
    history = api.get("/history", params={"limit": 100})
    pending = api.get("/approvals", params={"state": "PENDING_REVIEW", "limit": 100})
except api.ApiError as exc:
    show_error(exc)
    st.stop()

metric_row([
    ("GitHub", f"@{account['login']}" if account else "Not connected"),
    ("Write access", "Granted" if account and account["can_write"] else "Read-only"),
    ("Analyses", str(len(history))),
    ("Awaiting your approval", str(len(pending))),
])
if not account:
    st.info("Start by connecting GitHub on the **GitHub** page.")
if pending:
    st.warning(f"{len(pending)} proposal(s) are waiting for your decision on the **Approvals** page.")
st.subheader("Recent activity")
if history:
    st.dataframe(
        [{"When": fmt_dt(h["created_at"]), "Type": h["kind"], "Repository": h["repository"], "File": h["file_path"],
          "Status": h["status"], "Result": h["decision"]} for h in history[:10]],
        use_container_width=True, hide_index=True,
    )
else:
    st.caption("Nothing yet.")
