"""Scan text for credentials; findings are redacted."""

from __future__ import annotations

from pydantic import Field

from app.core.constants import DEFAULT_MAX_SOURCE_FILE_BYTES
from app.guardrails.secret_detection import find_secrets
from app.schemas.common import SecretFindingModel, StrictModel

TOOL_NAME = "inspect_secrets"


class InspectSecretsInput(StrictModel):
    text: str = Field(max_length=DEFAULT_MAX_SOURCE_FILE_BYTES * 2)


class InspectSecretsOutput(StrictModel):
    has_secrets: bool
    findings: list[SecretFindingModel]


def run(params: InspectSecretsInput) -> InspectSecretsOutput:
    findings = [SecretFindingModel(rule=f.rule, line=f.line, preview=f.preview) for f in find_secrets(params.text)]
    return InspectSecretsOutput(has_secrets=bool(findings), findings=findings)
