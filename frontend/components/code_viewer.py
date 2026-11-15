"""Source code viewer. Repository content is untrusted and rendered only as code."""

from __future__ import annotations

from typing import Any, Mapping

import streamlit as st

_LANG = {"shell": "bash", "csharp": "csharp", "cpp": "cpp", "dockerfile": "docker", "makefile": "makefile"}


def render_code(file: Mapping[str, Any]) -> None:
    findings = file.get("secret_findings") or []
    if findings:
        lines = ", ".join(str(f["line"]) for f in findings[:10])
        st.warning(f"Possible credentials detected (lines {lines}). Values are redacted before any AI analysis.")
    st.caption(f"{file['path']} · {file.get('language') or 'unknown'} · {file.get('line_count')} lines · blob {str(file.get('blob_sha'))[:8]}")
    language = _LANG.get(file.get("language") or "", file.get("language"))
    st.code(file["content"], language=language, line_numbers=True)
