import streamlit as st

from components.findings import render_findings
from components.layout import page_header, show_error
from lib import api_client as api
from lib import auth
from lib.formatting import fmt_dt

auth.require_login()
page_header("History", "Your past analyses and proposals.")
kind = st.selectbox("Type", ["All", "review", "comment", "logging"])
try:
    rows = api.get("/history", params={"limit": 50, **({"kind": kind} if kind != "All" else {})})
except api.ApiError as exc:
    show_error(exc)
    st.stop()
if not rows:
    st.info("Nothing here yet.")
    st.stop()
st.dataframe(
    [{"When": fmt_dt(r["created_at"]), "Type": r["kind"], "Repository": r["repository"], "File": r["file_path"],
      "Status": r["status"], "Result": r["decision"], "ID": r["id"]} for r in rows],
    use_container_width=True, hide_index=True,
)
reviews = [r for r in rows if r["kind"] == "review" and r["status"] == "succeeded"]
if reviews:
    st.subheader("Open a review")
    pick = st.selectbox("Review", reviews, format_func=lambda r: f"{fmt_dt(r['created_at'])} · {r['file_path']}")
    try:
        review = api.get(f"/reviews/{pick['id']}")
        st.write(review["reasoning"])
        render_findings(review["findings"], key="h")
    except api.ApiError as exc:
        show_error(exc)
