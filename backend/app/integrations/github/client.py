"""Dedicated GitHub REST client.

* Token is held privately and never appears in ``repr``, logs or errors.
* Only allowlisted (method, path) operations can be sent.
* Read-only by default; writes need ``allow_writes=True`` (separate instance).
* Bounded retries for GET only; writes are never retried.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Protocol

from app.core.constants import GITHUB_API_BASE_URL, GITHUB_API_VERSION, HTTP_USER_AGENT
from app.integrations.github.exceptions import (
    ForbiddenOperationError,
    GitHubAuthError,
    GitHubConflictError,
    GitHubError,
    GitHubNotFoundError,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubServerError,
    GitHubTransportError,
    GitHubValidationError,
    TransportFailure,
)
from app.integrations.github.rate_limits import (
    RateLimitInfo,
    parse_rate_limit,
    parse_retry_after,
    seconds_until_reset,
)

logger = logging.getLogger("app.integrations.github")

_SEG = r"[A-Za-z0-9_.-]+"
_REPO = rf"/repos/{_SEG}/{_SEG}"
_ALLOWED: dict[str, tuple[re.Pattern[str], ...]] = {
    "GET": tuple(
        re.compile(p)
        for p in (
            r"^/user$",
            rf"^{_REPO}$",
            rf"^{_REPO}/branches/.+$",
            rf"^{_REPO}/git/commits/[0-9a-f]{{40,64}}$",
            rf"^{_REPO}/git/trees/[0-9a-f]{{40,64}}$",
            rf"^{_REPO}/git/blobs/[0-9a-f]{{40,64}}$",
            rf"^{_REPO}/git/ref/heads/.+$",
            rf"^{_REPO}/contents/.+$",
            rf"^{_REPO}/commits$",
            rf"^{_REPO}/issues$",
            rf"^{_REPO}/issues/\d+$",
            rf"^{_REPO}/pulls$",
            rf"^{_REPO}/pulls/\d+$",
        )
    ),
    "POST": tuple(re.compile(p) for p in (rf"^{_REPO}/issues$", rf"^{_REPO}/git/refs$", rf"^{_REPO}/pulls$")),
    "PUT": (re.compile(rf"^{_REPO}/contents/.+$"),),
}
_BAD_PATH_RE = re.compile(r"[\x00-\x20\x7f?#\\]|%2e|%2f|%5c", re.IGNORECASE)


@dataclass(frozen=True)
class RawResponse:
    status: int
    headers: Mapping[str, str]  # lower-case keys
    body: bytes


class HttpTransport(Protocol):
    async def send(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str] | None,
        json_body: Any | None,
        timeout: float,
    ) -> RawResponse:
        """Send a request. Raise ``TransportFailure`` on timeouts/connection errors."""
        ...


class HttpxTransport:
    """Default transport. httpx is imported lazily so the rest stays importable without it."""

    def __init__(self) -> None:
        import httpx

        self._httpx = httpx
        self._client = httpx.AsyncClient(follow_redirects=False)

    async def send(self, method, url, *, headers, params, json_body, timeout):  # type: ignore[no-untyped-def]
        try:
            resp = await self._client.request(
                method, url, headers=dict(headers), params=params, json=json_body, timeout=timeout
            )
        except self._httpx.HTTPError as exc:
            raise TransportFailure(type(exc).__name__) from None
        return RawResponse(resp.status_code, {k.lower(): v for k, v in resp.headers.items()}, resp.content)

    async def aclose(self) -> None:
        await self._client.aclose()


@dataclass(frozen=True)
class GitHubResponse:
    status: int
    data: Any
    headers: Mapping[str, str] = field(default_factory=dict)
    request_id: str | None = None
    rate_limit: RateLimitInfo | None = None


def as_mapping(data: Any, what: str = "response") -> Mapping[str, Any]:
    if not isinstance(data, dict):
        raise GitHubError(f"Unexpected GitHub {what} shape.")
    return data


class GitHubClient:
    def __init__(
        self,
        token: str,
        *,
        transport: HttpTransport | None = None,
        base_url: str = GITHUB_API_BASE_URL,
        allow_writes: bool = False,
        max_retries: int = 2,
        timeout: float = 15.0,
        max_rate_limit_wait: float = 30.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(token, str) or not token or re.search(r"\s", token):
            raise ValueError("A valid GitHub token is required.")
        if not base_url.startswith("https://"):
            raise ValueError("GitHub base URL must use https.")
        self.__token = token
        self._base_url = base_url.rstrip("/")
        self._transport = transport if transport is not None else HttpxTransport()
        self.allow_writes = allow_writes
        self._max_retries = max(0, max_retries)
        self._timeout = timeout
        self._max_wait = max_rate_limit_wait
        self._sleep = sleep
        self._clock = clock

    def __repr__(self) -> str:
        return f"GitHubClient(allow_writes={self.allow_writes})"

    def __reduce__(self):  # prevent accidental serialization of the token
        raise TypeError("GitHubClient cannot be pickled.")

    def _authorize(self, method: str, path: str) -> None:
        patterns = _ALLOWED.get(method)
        if patterns is None:
            raise ForbiddenOperationError("HTTP method is not permitted.")
        if method != "GET" and not self.allow_writes:
            raise ForbiddenOperationError("This GitHub client is read-only.")
        if not path.startswith("/") or _BAD_PATH_RE.search(path) or any(
            seg in {".", ".."} for seg in path.split("/")
        ):
            raise ForbiddenOperationError("Invalid GitHub API path.")
        if not any(p.match(path) for p in patterns):
            raise ForbiddenOperationError("GitHub operation is not on the allowlist.")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.__token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": HTTP_USER_AGENT,
        }

    def _scrub(self, text: str) -> str:
        return text.replace(self.__token, "[REDACTED]")[:300]

    def _interpret(self, raw: RawResponse) -> GitHubResponse:
        request_id = raw.headers.get("x-github-request-id")
        status = raw.status
        body: Any = None
        if raw.body:
            try:
                body = json.loads(raw.body)
            except ValueError:
                body = None
        if 200 <= status < 300:
            if raw.body and body is None:
                raise GitHubError("GitHub returned invalid JSON.", status=status, request_id=request_id)
            return GitHubResponse(status, body, raw.headers, request_id, parse_rate_limit(raw.headers))
        message = self._scrub(str(body.get("message", ""))) if isinstance(body, dict) else ""
        text = f"GitHub request failed ({status})" + (f": {message}" if message else "")
        if status == 401:
            raise GitHubAuthError(text, status=status, request_id=request_id)
        if status in (403, 429):
            info = parse_rate_limit(raw.headers)
            retry_after = parse_retry_after(raw.headers)
            limited = (
                status == 429
                or retry_after is not None
                or (info is not None and info.remaining == 0)
                or "rate limit" in message.lower()
            )
            if limited:
                wait = retry_after if retry_after is not None else seconds_until_reset(info, self._clock())
                raise GitHubRateLimitError(text, retry_after=wait, status=status, request_id=request_id)
            raise GitHubPermissionError(text, status=status, request_id=request_id)
        if status == 404:
            raise GitHubNotFoundError(text, status=status, request_id=request_id)
        if status == 409:
            raise GitHubConflictError(text, status=status, request_id=request_id)
        if status == 422:
            raise GitHubValidationError(text, status=status, request_id=request_id)
        if status >= 500:
            raise GitHubServerError(text, status=status, request_id=request_id)
        raise GitHubError(text, status=status, request_id=request_id)

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json_body: Any | None = None,
    ) -> GitHubResponse:
        method = method.upper()
        self._authorize(method, path)
        attempts = (self._max_retries + 1) if method == "GET" else 1
        url = self._base_url + path
        for attempt in range(attempts):
            last = attempt + 1 >= attempts
            try:
                raw = await self._transport.send(
                    method, url, headers=self._headers(), params=params,
                    json_body=json_body, timeout=self._timeout,
                )
            except TransportFailure as exc:
                if last:
                    raise GitHubTransportError(
                        f"Network error contacting GitHub ({exc}).", outcome_unknown=method != "GET"
                    ) from None
                await self._backoff(attempt)
                continue
            try:
                response = self._interpret(raw)
            except GitHubServerError:
                if last:
                    raise
                await self._backoff(attempt)
                continue
            except GitHubRateLimitError as exc:
                if last or exc.retry_after is None or exc.retry_after > self._max_wait:
                    raise
                await self._sleep(exc.retry_after)
                continue
            logger.info(
                "github_request", extra={"method": method, "status": response.status, "request_id": response.request_id}
            )
            return response
        raise GitHubError("GitHub request failed.")  # pragma: no cover

    async def _backoff(self, attempt: int) -> None:
        await self._sleep(min(8.0, 0.5 * (2**attempt)) + random.uniform(0, 0.25))

    async def aclose(self) -> None:
        close = getattr(self._transport, "aclose", None)
        if close is not None:
            await close()
