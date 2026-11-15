import streamlit as st

from components.charts import bar_chart
from components.layout import page_header, show_error
from lib import api_client as api
from lib import auth
from lib.formatting import pct

auth.require_role("admin", "recruiter")
page_header("Quality", "Mean score and latency per evaluation type (latest run of each).")
try:
    data = api.get("/evaluations/overview")
except api.ApiError as exc:
    show_error(exc)
    st.stop()
latest = data["latest_by_kind"]
if not latest:
    st.info("No completed evaluations yet.")
    st.stop()
bar_chart({k: v["mean_score"] for k, v in latest.items()}, title="Mean score (%)")
st.dataframe([{"Suite": k, "Cases": v["total"], "Passed": v["passed"], "Errors": v["errors"], "Pass rate": pct(v["pass_rate"]),
               "Mean score": pct(v["mean_score"]), "p50 latency (ms)": v["latency_p50_ms"], "p95 latency (ms)": v["latency_p95_ms"],
               "Model": v.get("model")} for k, v in latest.items()], use_container_width=True, hide_index=True)
st.caption("Errors are cases that could not be scored (for example the model was unavailable); they are not counted as passes or failures.")
