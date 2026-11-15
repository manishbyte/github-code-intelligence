"""Review findings list."""

from __future__ import annotations

from typing import Any, Sequence

import streamlit as st

from lib.formatting import SEVERITY_BADGE


def render_findings(findings: Sequence[dict[str, Any]], *, key: str, selectable: bool = False) -> list[str]:
    """Render findings; returns the ids the user ticked (when ``selectable``)."""
    chosen: list[str] = []
    for f in findings:
        title = f"{SEVERITY_BADGE.get(f['severity'], f['severity'])} · {f['category']} · {f['title']} (lines {f['start_line']}–{f['end_line']})"
        with st.expander(title):
            st.caption(f"Confidence {f['confidence']:.0%} · validated against the file content")
            st.write(f["description"])
            st.markdown("**Evidence**")
            st.code(f["evidence"], language="text")
            if f.get("suggested_fix"):
                st.markdown("**Suggested fix**")
                st.write(f["suggested_fix"])
            if selectable and st.checkbox("Include in issue", value=True, key=f"{key}-{f['id']}"):
                chosen.append(f["id"])
    return chosen
