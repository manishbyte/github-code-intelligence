"""Groq chat-completions client (JSON mode). The model name comes from configuration."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

from app.core.constants import HTTP_USER_AGENT
from app.core.exceptions import LLMError
from app.integrations.github.client import HttpTransport
from app.integrations.github.exceptions import TransportFailure

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


@dataclass(frozen=True)
class LLMResult:
    text: str
    usage: dict[str, Any]
    latency_ms: int
    model: str


class GroqClient:
    def __init__(self, api_key: str, model: str, transport: HttpTransport, *, timeout: float = 60.0, max_retries: int = 2) -> None:
        if not api_key or not model:
            raise LLMError("The language model is not configured (GROQ_API_KEY / GROQ_MODEL).")
        self.__api_key = api_key
        self.model = model
        self._transport = transport
        self._timeout = timeout
        self._max_retries = max_retries

    def __repr__(self) -> str:
        return f"GroqClient(model={self.model!r})"

    async def complete_json(self, system: str, user: str, *, max_tokens: int = 2048) -> LLMResult:
        body = {
            "model": self.model, "temperature": 0, "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        headers = {"Authorization": f"Bearer {self.__api_key}", "Content-Type": "application/json", "User-Agent": HTTP_USER_AGENT}
        started = time.perf_counter()
        for attempt in range(self._max_retries + 1):
            last = attempt == self._max_retries
            try:
                resp = await self._transport.send("POST", GROQ_URL, headers=headers, params=None, json_body=body, timeout=self._timeout)
            except TransportFailure:
                if last:
                    raise LLMError("The language model request failed (network).") from None
                await asyncio.sleep(min(8.0, 1.0 * 2**attempt))
                continue
            if resp.status == 200:
                try:
                    data = json.loads(resp.body)
                    text = data["choices"][0]["message"]["content"]
                except (ValueError, KeyError, IndexError, TypeError):
                    raise LLMError("The language model returned an unexpected response.") from None
                return LLMResult(str(text), dict(data.get("usage") or {}), int((time.perf_counter() - started) * 1000), self.model)
            if resp.status in (429, 500, 502, 503, 504) and not last:
                wait = float(resp.headers.get("retry-after", 2**attempt))
                await asyncio.sleep(min(20.0, max(0.5, wait)))
                continue
            raise LLMError(f"The language model request failed ({resp.status}).")
        raise LLMError("The language model request failed.")  # pragma: no cover
