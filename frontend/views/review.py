import streamlit as st

from components.approval_card import render_approval
from components.layout import page_header, show_error
from components.findings import render_findings
from lib import api_client as api
from lib import auth

auth.require_login()
page_header("Review & propose", "Nothing is posted to GitHub from this page. Every proposal goes to Approvals first.")

try:
    repos = api.get("/github/repositories")
except api.ApiError as exc:
    show_error(exc)
    st.stop()
if not repos:
    st.info("Inspect a repository on the **Repository** page first.")
    st.stop()

ids = [r["id"] for r in repos]
index = ids.index(st.session_state["repo_id"]) if st.session_state.get("repo_id") in ids else 0
repo = st.selectbox("Repository", repos, index=index, format_func=lambda r: f"{r['owner']}/{r['name']}")
st.session_state["repo_id"] = repo["id"]
try:
    tree = api.get(f"/repositories/{repo['id']}/tree")
except api.ApiError as exc:
    show_error(exc)
    st.stop()

query = st.text_input("Filter files", placeholder="e.g. .py").strip().lower()
choices = [e["path"] for e in tree["entries"] if e["kind"] == "file" and query in e["path"].lower()][:500]
if not choices:
    st.info("No files match.")
    st.stop()
path = st.selectbox("File", choices)
body = {"repository_id": repo["id"], "file_path": path, "commit_sha": tree["commit_sha"]}

c1, c2, c3 = st.columns(3)
actions = (
    (c1, "Review code", "/reviews", "review"),
    (c2, "Propose comments", "/code-changes/comments", "comments"),
    (c3, "Propose logging", "/code-changes/logging", "logging"),
)
for col, label, endpoint, key in actions:
    if col.button(label, key=f"run-{key}", use_container_width=True):
        with st.spinner("Working… (AI output is validated before you see it)"):
            try:
                st.session_state["result"] = {"kind": key, "data": api.post(endpoint, json=body)}
            except api.ApiError as exc:
                st.session_state.pop("result", None)
                show_error(exc)

result = st.session_state.get("result")
if not result:
    st.stop()
st.divider()
data = result["data"]

if result["kind"] == "review":
    st.subheader(f"Review of {data['file_path']}")
    for w in data["warnings"]:
        st.warning(w)
    st.write(data["reasoning"])
    if data["findings"]:
        chosen = render_findings(data["findings"], key="f", selectable=True)
        if st.button("Draft an issue from selected findings", type="primary", disabled=not chosen):
            with st.spinner("Drafting and checking for duplicates…"):
                try:
                    proposal = api.post(f"/reviews/{data['id']}/issue-proposals", json={"finding_ids": chosen})
                    st.session_state["result"] = {"kind": "issue", "data": proposal}
                    st.rerun()
                except api.ApiError as exc:
                    show_error(exc)
    else:
        st.success("No validated problems were found.")
elif result["kind"] == "issue":
    st.subheader("Issue proposal")
    st.success("Draft created. Review it and decide on the **Approvals** page — or right here:")
    approval = api.get(f"/approvals/{data['approval']['id']}")
    render_approval(approval, key="rv-issue", expanded=True)
else:
    st.subheader("Proposed change")
    approval = api.get(f"/approvals/{data['approval']['id']}")
    render_approval(approval, key="rv-change", expanded=True)
