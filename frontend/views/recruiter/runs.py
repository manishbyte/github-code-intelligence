import streamlit as st

from components.layout import page_header, show_error
from lib import api_client as api
from lib import auth
from lib.formatting import fmt_dt, pct
from lib.permissions import can_run_evaluation

user = auth.require_role("admin", "recruiter")
page_header("Evaluation runs")

if can_run_evaluation(user):
    with st.form("start"):
        kind = st.selectbox("Suite", ["all", "tree", "patch", "safety", "issue", "review", "comment", "logging"])
        model = st.text_input("Model override (optional)", placeholder="defaults to GROQ_MODEL")
        go = st.form_submit_button("Start run", type="primary")
    if go:
        try:
            api.post("/evaluations/runs", json={"kind": kind, "model": model or None})
            st.success("Queued. A background worker will execute it.")
        except api.ApiError as exc:
            show_error(exc)

try:
    runs = api.get("/evaluations/runs", params={"limit": 30})
except api.ApiError as exc:
    show_error(exc)
    st.stop()
if st.button("🔄 Refresh"):
    st.rerun()
st.dataframe([{"When": fmt_dt(r["created_at"]), "Suite": r["kind"], "Model": r["model"], "Status": r["status"],
               "Pass rate": pct(((r["metrics"] or {}).get("overall") or {}).get("pass_rate")), "ID": r["id"]} for r in runs],
             use_container_width=True, hide_index=True)
if runs:
    pick = st.selectbox("Run details", runs, format_func=lambda r: f"{fmt_dt(r['created_at'])} · {r['kind']} · {r['status']}")
    if pick["error"]:
        st.error(pick["error"])
    if pick["regression"]:
        reg = pick["regression"]
        (st.error if reg["regressed"] else st.success)(
            "Regression detected versus the previous run." if reg["regressed"] else "No regression versus the previous run.")
        if reg["regressions"]:
            st.dataframe(reg["regressions"], use_container_width=True, hide_index=True)
    if pick["status"] == "succeeded":
        for fmt in ("csv", "md", "json"):
            try:
                st.download_button(f"Download {fmt.upper()}", api.get(f"/evaluations/reports/{pick['id']}/export", params={"format": fmt}, text=True),
                                   file_name=f"evaluation-{pick['id']}.{fmt}", key=f"dl-{fmt}")
            except api.ApiError as exc:
                show_error(exc)
