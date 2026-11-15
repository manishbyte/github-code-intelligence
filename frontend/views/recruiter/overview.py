import streamlit as st

from components.charts import bar_chart
from components.layout import page_header, show_error
from components.recruiter import metric_row
from lib import api_client as api
from lib import auth
from lib.formatting import fmt_dt, pct

auth.require_role("admin", "recruiter")
page_header("Evaluation overview", "Latest measured quality and safety of the system.")
try:
    data = api.get("/evaluations/overview")
except api.ApiError as exc:
    show_error(exc)
    st.stop()
latest = data["latest_by_kind"]
if not latest:
    st.info("No evaluation has completed yet. An administrator can start one on the Runs page.")
    st.stop()
metric_row([("Runs", str(data["total_runs"])), ("Safety pass rate", pct(data["safety_pass_rate"])),
            ("Kinds evaluated", str(len(latest)))])
bar_chart({k: v["pass_rate"] for k, v in latest.items()}, title="Pass rate by evaluation type (%)")
st.subheader("Recent runs")
st.dataframe([{"When": fmt_dt(r["created_at"]), "Type": r["kind"], "Model": r["model"], "Pass rate": pct(r["pass_rate"]),
               "Regression": "⚠️ yes" if r["regressed"] else "no"} for r in data["recent_runs"]],
             use_container_width=True, hide_index=True)
