"""HTTP client for the backend API.

API tokens are kept in Streamlit *server-side* session state (``st.session_state``) and are never
sent to the browser. Requests authenticate with ``Authorization: Bearer``; the refresh token is sent
as a cookie to ``/auth/*`` together with the configured ``Origin`` header.
"""

from __future__ import annotations

import os
from http.cookies import SimpleCookie
from typing import Any

import httpx
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8008").rstrip("/")
FRONTEND_ORIGIN = os.environ.get("FRONTEND_BASE_URL", "http://localhost:8502").rstrip("/")
API = f"{API_BASE_URL}/api/v1"
ACCESS_COOKIE, REFRESH_COOKIE = "gci_access", "gci_refresh"


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@st.cache_resource
def _http() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0), follow_redirects=False)


def clear_session() -> None:
    for key in ("access", "refresh", "user"):
        st.session_state.pop(key, None)


def _store_tokens(resp: httpx.Response) -> None:
    values: dict[str, str] = {}
    for header in resp.headers.get_list("set-cookie"):
        jar = SimpleCookie()
        jar.load(header)
        values.update({k: m.value for k, m in jar.items()})
    if values.get(ACCESS_COOKIE):
        st.session_state["access"] = values[ACCESS_COOKIE]
    if values.get(REFRESH_COOKIE):
        st.session_state["refresh"] = values[REFRESH_COOKIE]


def _send(method: str, path: str, *, json: Any, params: dict | None, auth: bool) -> httpx.Response:
    headers = {"Origin": FRONTEND_ORIGIN, "Accept": "application/json"}
    cookies = None
    if auth and st.session_state.get("access"):
        headers["Authorization"] = f"Bearer {st.session_state['access']}"
    if path.startswith("/auth/") and st.session_state.get("refresh"):
        cookies = {REFRESH_COOKIE: st.session_state["refresh"]}
    try:
        return _http().request(method, API + path, json=json, params=params, headers=headers, cookies=cookies)
    except httpx.HTTPError:
        raise ApiError(0, "network_error", "The API is unreachable. Please try again.") from None


def _refresh() -> bool:
    if not st.session_state.get("refresh"):
        return False
    resp = _send("POST", "/auth/refresh", json=None, params=None, auth=False)
    if resp.status_code != 200:
        clear_session()
        return False
    _store_tokens(resp)
    return True


def request(method: str, path: str, *, json: Any = None, params: dict | None = None, auth: bool = True, text: bool = False) -> Any:
    resp = _send(method, path, json=json, params=params, auth=auth)
    if resp.status_code == 401 and auth and _refresh():
        resp = _send(method, path, json=json, params=params, auth=auth)
    if resp.status_code < 400:
        _store_tokens(resp)
    if resp.status_code >= 400:
        try:
            err = resp.json().get("error", {})
        except ValueError:
            err = {}
        if resp.status_code == 401 and auth:
            clear_session()
        raise ApiError(resp.status_code, err.get("code", "error"), err.get("message", f"Request failed ({resp.status_code})."))
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.text if text else resp.json()


def get(path: str, **kw: Any) -> Any:
    return request("GET", path, **kw)


def post(path: str, **kw: Any) -> Any:
    return request("POST", path, **kw)


def patch(path: str, **kw: Any) -> Any:
    return request("PATCH", path, **kw)


def delete(path: str, **kw: Any) -> Any:
    return request("DELETE", path, **kw)
