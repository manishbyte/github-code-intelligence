"""Session helpers: login, registration, logout, and page guards."""

from __future__ import annotations

from typing import Any

import streamlit as st

from lib import api_client as api


def login(email: str, password: str) -> dict[str, Any]:
    data = api.post("/auth/login", json={"email": email, "password": password}, auth=False)
    st.session_state["user"] = data["user"]
    return data["user"]


def register(email: str, password: str, display_name: str) -> dict[str, Any]:
    return api.post("/auth/register", json={"email": email, "password": password, "display_name": display_name}, auth=False)["user"]


def logout() -> None:
    try:
        api.post("/auth/logout")
    except api.ApiError:
        pass
    api.clear_session()


def current_user() -> dict[str, Any] | None:
    """The signed-in user, verified against the API once per browser session."""
    if st.session_state.get("user"):
        return st.session_state["user"]
    if st.session_state.get("access") or st.session_state.get("refresh"):
        try:
            st.session_state["user"] = api.get("/auth/me")
            return st.session_state["user"]
        except api.ApiError:
            api.clear_session()
    return None


def require_login() -> dict[str, Any]:
    user = current_user()
    if user is None:
        st.warning("Please sign in to continue.")
        st.stop()
    return user


def require_role(*roles: str) -> dict[str, Any]:
    user = require_login()
    if user["role"] not in roles:
        st.error("You do not have access to this page.")
        st.stop()
    return user
