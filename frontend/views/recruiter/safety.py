import streamlit as st

from components.layout import page_header, show_error
from components.recruiter import metric_row
from lib import api_client as api
from lib import auth
from lib.formatting import pct

auth.require_role("admin", "recruiter")
page_header("Safety", "Prompt-injection, secret, path and URL guardrail checks.")
try:
    overview = api.get("/evaluations/overview")
    safety = overview["latest_by_kind"].get("safety")
    if not safety:
        st.info("No safety evaluation has completed yet.")
        st.stop()
    cases = api.get(f"/evaluations/runs/{safety['run_id']}/cases")
except api.ApiError as exc:
    show_error(exc)
    st.stop()
rows = [c for c in cases if c["kind"] == "safety"]
metric_row([("Pass rate", pct(safety["pass_rate"])), ("Cases", str(safety["total"])), ("Failed", str(safety["failed"]))])
by_type: dict[str, list[bool]] = {}
for c in rows:
    by_type.setdefault((c["details"] or {}).get("type", "unknown"), []).append(c["passed"])
st.dataframe([{"Check": t, "Cases": len(v), "Passed": sum(v), "Pass rate": pct(sum(v) / len(v))} for t, v in sorted(by_type.items())],
             use_container_width=True, hide_index=True)
failed = [c for c in rows if not c["passed"]]
if failed:
    st.error(f"{len(failed)} safety case(s) failed")
    st.dataframe([{"Case": c["case_key"], "Details": str(c["details"])} for c in failed], use_container_width=True, hide_index=True)
else:
    st.success("All safety cases passed in the latest run.")
