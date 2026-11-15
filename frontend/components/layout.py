"""Shared layout: headers, sidebar and error display."""

from __future__ import annotations

from typing import Any, Mapping

import streamlit as st

from lib import auth
from lib.api_client import ApiError


def page_header(title: str, caption: str | None = None) -> None:
    st.title(title)
    if caption:
        st.caption(caption)


def show_error(exc: ApiError) -> None:
    st.error(exc.message)
    if exc.code in {"github_not_connected", "github_token_invalid"}:
        st.info("Open the **GitHub** page to connect (or reconnect) your account.")


def sidebar(user: Mapping[str, Any]) -> None:
    with st.sidebar:
        st.markdown(f"**{user['display_name']}**")
        st.caption(f"{user['email']} · {user['role']}")
        if st.button("Sign out", use_container_width=True):
            auth.logout()
            st.rerun()
