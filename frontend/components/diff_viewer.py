"""Unified diff viewer."""

from __future__ import annotations

import streamlit as st


def render_diff(diff: str) -> None:
    added = sum(1 for ln in diff.split("\n") if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in diff.split("\n") if ln.startswith("-") and not ln.startswith("---"))
    st.caption(f"+{added} / −{removed} lines")
    st.code(diff, language="diff")
