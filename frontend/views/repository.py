import streamlit as st

from components.code_viewer import render_code
from components.layout import page_header, show_error
from components.tree_view import render_tree
from lib import api_client as api
from lib import auth
from lib.formatting import fmt_dt, short_sha

auth.require_login()
page_header("Repository explorer", "Public repositories only. The tree is pinned to a commit SHA.")

with st.form("inspect"):
    url = st.text_input("Repository URL", placeholder="https://github.com/owner/repo")
    go = st.form_submit_button("Inspect", type="primary")
if go:
    with st.spinner("Fetching the repository tree…"):
        try:
            result = api.post("/repositories/inspect", json={"repository_url": url})
            st.session_state["repo_id"] = result["repository"]["id"]
            if result["is_empty"]:
                st.warning("This repository is empty.")
        except api.ApiError as exc:
            show_error(exc)

try:
    repos = api.get("/github/repositories")
except api.ApiError as exc:
    show_error(exc)
    st.stop()
if not repos:
    st.info("Inspect a repository to get started.")
    st.stop()

ids = [r["id"] for r in repos]
index = ids.index(st.session_state["repo_id"]) if st.session_state.get("repo_id") in ids else 0
repo = st.selectbox("Repository", repos, index=index, format_func=lambda r: f"{r['owner']}/{r['name']}")
st.session_state["repo_id"] = repo["id"]
st.caption(f"{repo['html_url']} · default branch `{repo['default_branch']}` · inspected {fmt_dt(repo['last_inspected_at'])}")

try:
    tree = api.get(f"/repositories/{repo['id']}/tree")
except api.ApiError as exc:
    show_error(exc)
    st.stop()
st.caption(f"Commit {short_sha(tree['commit_sha'])} · {tree['file_count']} files · {tree['directory_count']} folders"
           + (f" · {tree['skipped_unsafe_entries']} unsafe entries skipped" if tree["skipped_unsafe_entries"] else ""))
shown = render_tree(tree["entries"], key="tree")

st.subheader("View a file")
files = [e["path"] for e in shown if e["kind"] == "file"][:500]
if files:
    path = st.selectbox("File", files)
    if st.button("Open file"):
        try:
            st.session_state["open_file"] = api.get(f"/repositories/{repo['id']}/files/{path}")
        except api.ApiError as exc:
            show_error(exc)
    file = st.session_state.get("open_file")
    if file and file["path"] == path:
        render_code(file)
