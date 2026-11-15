import streamlit as st

from components.approval_card import render_approval
from components.layout import page_header, show_error
from lib import api_client as api
from lib import auth

auth.require_login()
page_header("Approvals", "Only content you approve here can ever be published to GitHub.")
state = st.selectbox("Show", ["All", "PENDING_REVIEW", "APPROVED", "PUBLISHED", "REJECTED", "FAILED", "EXPIRED"])
try:
    rows = api.get("/approvals", params={"limit": 50, **({"state": state} if state != "All" else {})})
except api.ApiError as exc:
    show_error(exc)
    st.stop()
if not rows:
    st.info("No approval requests.")
for a in rows:
    render_approval(a, key=a["id"], expanded=a["state"] in ("PENDING_REVIEW", "APPROVED"))
