from __future__ import annotations

import uuid

from app.agents.logging_agent import LoggingAgent
from app.workflows.comment_generation.graph import compile_code_change_graph, run_code_change
from app.workflows.comment_generation.state import CodeChangeState
from app.workflows.common import WorkflowDeps
from app.workflows.logging_generation.nodes import LoggingNodes


def build_graph(deps: WorkflowDeps):
    return compile_code_change_graph(LoggingNodes(deps, LoggingAgent(deps.require_llm())))


async def run_logging_generation(deps: WorkflowDeps, *, repository_id: uuid.UUID, file_path: str, commit_sha: str | None) -> CodeChangeState:
    nodes = LoggingNodes(deps, LoggingAgent(deps.require_llm()))
    return await run_code_change(deps, nodes, repository_id=repository_id, file_path=file_path, commit_sha=commit_sha)
