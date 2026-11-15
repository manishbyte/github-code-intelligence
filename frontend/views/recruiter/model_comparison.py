import streamlit as st

from components.layout import page_header, show_error
from lib import api_client as api
from lib import auth
from lib.formatting import pct

auth.require_role("admin", "recruiter")
page_header("Model comparison", "Latest result per suite for each model that has been evaluated.")
try:
    data = api.get("/evaluations/comparison")
except api.ApiError as exc:
    show_error(exc)
    st.stop()
models = data["models"]
if not models:
    st.info("No completed evaluations yet.")
    st.stop()
kinds = sorted({k for m in models for k in m["kinds"]})
st.dataframe([{"Model": m["model"], "Runs": m["runs"], **{k: pct(m["kinds"].get(k, {}).get("pass_rate")) for k in kinds}} for m in models],
             use_container_width=True, hide_index=True)
st.caption("Pass rate per suite. Deterministic suites (tree, patch, safety, issue) do not depend on the model.")
