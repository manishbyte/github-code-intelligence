import streamlit as st

from components.layout import page_header, show_error
from lib import api_client as api
from lib import auth
from lib.formatting import fmt_dt

auth.require_role("admin", "recruiter")
page_header("Failures", "Failed and errored cases for a chosen run.")
try:
    runs = [r for r in api.get("/evaluations/runs", params={"limit": 30}) if r["status"] == "succeeded"]
except api.ApiError as exc:
    show_error(exc)
    st.stop()
if not runs:
    st.info("No completed runs.")
    st.stop()
run = st.selectbox("Run", runs, format_func=lambda r: f"{fmt_dt(r['created_at'])} · {r['kind']} · {r['model'] or 'deterministic'}")
try:
    cases = api.get(f"/evaluations/runs/{run['id']}/cases", params={"failed_only": True})
except api.ApiError as exc:
    show_error(exc)
    st.stop()
if not cases:
    st.success("No failures in this run.")
for c in cases:
    err = (c["details"] or {}).get("error")
    with st.expander(f"{'⚠️ error' if err else '❌ failed'} · {c['kind']} · {c['case_key']}"):
        st.write(f"Score {c['score']:.2f} · {c['latency_ms']} ms")
        st.json(c["details"])
