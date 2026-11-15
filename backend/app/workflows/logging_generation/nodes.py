from __future__ import annotations

from typing import Any

from app.agents.patch_agent import ValidEdit, detect_logging_convention, validate_logging_edits
from app.schemas.code_change import RawEdits
from app.workflows.comment_generation.nodes import CodeChangeNodes
from app.workflows.comment_generation.state import CodeChangeState
from app.workflows.logging_generation import prompts as logging_prompts


class LoggingNodes(CodeChangeNodes):
    prompts = logging_prompts

    def _conventions(self, language: str, content: str) -> dict[str, Any]:
        return detect_logging_convention(language, content)

    def _validate(self, language: str, content: str, raw: RawEdits, conventions: dict[str, Any]) -> tuple[list[ValidEdit], list[str]]:
        return validate_logging_edits(language, content, raw.edits, conventions)

    async def _propose(self, state: CodeChangeState):
        return await self.agent.propose(file_path=state["file_path"], language=state["language"],
                                        content=state["redacted"], conventions=state["conventions"])
