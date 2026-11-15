"""Strict parsing and sanitization of LLM output."""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.core.exceptions import OutputValidationError

T = TypeVar("T", bound=BaseModel)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TAG_RE = re.compile(r"(?is)<\s*(script|iframe|object|embed|style)\b.*?>.*?<\s*/\s*\1\s*>|<\s*(script|iframe|object|embed)\b[^>]*>")
MAX_OUTPUT_CHARS = 60_000


def sanitize_text(text: str, *, max_length: int) -> str:
    """Strip control characters and active HTML; enforce a length cap."""
    cleaned = _TAG_RE.sub("", _CONTROL_RE.sub("", text)).strip()
    return cleaned[:max_length]


def extract_json_object(text: str) -> dict:
    if not isinstance(text, str) or len(text) > MAX_OUTPUT_CHARS:
        raise OutputValidationError("Model output is missing or too large.")
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.IGNORECASE).strip()
    try:
        data = json.loads(candidate)
    except ValueError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            raise OutputValidationError("Model output is not valid JSON.") from None
        try:
            data = json.loads(candidate[start : end + 1])
        except ValueError:
            raise OutputValidationError("Model output is not valid JSON.") from None
    if not isinstance(data, dict):
        raise OutputValidationError("Model output must be a JSON object.")
    return data


def parse_structured_output(text: str, model: type[T]) -> T:
    data = extract_json_object(text)
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        raise OutputValidationError("Model output failed schema validation: " + ", ".join(fields)[:300]) from None
