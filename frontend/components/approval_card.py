"""Approval review card: shows exactly what will be published and the human decision controls."""

from __future__ import annotations

from typing import Any, Mapping

import streamlit as st

from components.code_viewer import render_code  # noqa: F401  (re-exported for pages)
from components.diff_viewer import render_diff
from components.layout import show_error
from lib import api_client as api
from lib.formatting import STATE_BADGE, fmt_dt, short_sha


def _artifact(approval: Mapping[str, Any]) -> dict[str, Any] | None:
    if not approval.get("artifact_id"):
        return None
    prefix = "issue-proposals" if approval["action_type"] == "create_issue" else "code-changes"
    try:
        return api.get(f"/{prefix}/{approval['artifact_id']}")
    except api.ApiError as exc:
        show_error(exc)
        return None


def render_approval(approval: Mapping[str, Any], *, key: str, expanded: bool = False) -> None:
    label = f"{STATE_BADGE.get(approval['state'], approval['state'])} · {approval['action_type']} · {approval['owner']}/{approval['repo']} · {fmt_dt(approval['created_at'])}"
    with st.expander(label, expanded=expanded):
        artifact = _artifact(approval)
        if approval["action_type"] == "create_issue":
            title = approval["payload"]["title"]
            st.subheader(title)
            for dup in (artifact or {}).get("duplicate_candidates", []):
                st.warning(f"Possible duplicate: #{dup['number']} {dup['title']} ({dup['similarity']:.0%} similar) — {dup['url']}")
            st.caption("Exact issue body that will be posted (shown as plain text):")
            st.code(approval["payload"]["body"], language="markdown")
        elif artifact:
            st.subheader(f"{artifact['kind'].replace('_', ' ').title()} for {artifact['file_path']}")
            st.write(artifact["summary"])
            render_diff(artifact["diff"])
            for c in artifact["quality"]["checks"]:
                st.write(f"{'✅' if c['status'] == 'passed' else '⏭️' if c['status'] == 'skipped' else '❌'} {c['name']}: {c['message']}")
            p = approval["payload"]
            st.caption(f"Will create branch `{p['branch']['branch']}` from {short_sha(p['branch']['from_sha'])}, commit to `{p['commit']['path']}`, "
                       f"and open a pull request into `{p['pull_request']['base']}`.")
        st.caption(f"Content digest {approval['payload_digest'][:16]}… · expires {fmt_dt(approval['expires_at'])}")

        state = approval["state"]
        if state == "PENDING_REVIEW":
            c1, c2 = st.columns(2)
            if c1.button("✅ Approve", key=f"{key}-approve", type="primary", use_container_width=True):
                _decide(approval, "approve")
            if c2.button("⛔ Reject", key=f"{key}-reject", use_container_width=True):
                _decide(approval, "reject")
        elif state == "APPROVED":
            st.info("Approved. Nothing has been written to GitHub yet.")
            if st.button("🚀 Publish to GitHub", key=f"{key}-publish", type="primary"):
                with st.spinner("Publishing and verifying on GitHub…"):
                    try:
                        api.post(f"/approvals/{approval['id']}/publish")
                        st.rerun()
                    except api.ApiError as exc:
                        show_error(exc)
        for action in approval.get("actions", []):
            icon = "✅" if action["status"] == "completed" else "⚠️"
            link = f" — {action['github_url']}" if action.get("github_url") else ""
            st.write(f"{icon} {action['step']}: {action['status']}{link}")


def _decide(approval: Mapping[str, Any], verb: str) -> None:
    try:
        api.post(f"/approvals/{approval['id']}/{verb}", json={"displayed_payload_digest": approval["payload_digest"]})
        st.rerun()
    except api.ApiError as exc:
        show_error(exc)
