from __future__ import annotations

import uuid
from typing import Any

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.agents.comment_agent import CommentAgent
from app.core.exceptions import AppError
from app.models.analysis_run import AnalysisRun
from app.workflows.comment_generation.nodes import CodeChangeNodes
from app.workflows.comment_generation.state import CodeChangeState
from app.workflows.common import WorkflowDeps


def compile_code_change_graph(nodes: CodeChangeNodes):
    g = StateGraph(CodeChangeState)
    for name in ("load_file", "inspect", "generate", "build_patch", "persist"):
        g.add_node(name, getattr(nodes, name))
    g.add_edge(START, "load_file")
    g.add_edge("load_file", "inspect")
    g.add_edge("inspect", "generate")
    g.add_edge("generate", "build_patch")
    g.add_edge("build_patch", "persist")
    g.add_edge("persist", END)
    return g.compile()


async def run_code_change(deps: WorkflowDeps, nodes: CodeChangeNodes, *, repository_id: uuid.UUID, file_path: str, commit_sha: str | None) -> CodeChangeState:
    try:
        return await compile_code_change_graph(nodes).ainvoke(
            {"repository_id": str(repository_id), "file_path": file_path, "commit_sha": commit_sha})
    except Exception as exc:
        await deps.db.rollback()
        if nodes.run_id is not None:
            run = (await deps.db.execute(select(AnalysisRun).where(AnalysisRun.id == nodes.run_id, AnalysisRun.user_id == deps.user_id))).scalar_one_or_none()
            if run is not None:
                run.status, run.completed_at = "failed", deps.now()
                run.error = exc.message if isinstance(exc, AppError) else "Internal error during generation."
                await deps.db.commit()
        raise


async def run_comment_generation(deps: WorkflowDeps, *, repository_id: uuid.UUID, file_path: str, commit_sha: str | None) -> CodeChangeState:
    nodes = CodeChangeNodes(deps, CommentAgent(deps.require_llm()))
    return await run_code_change(deps, nodes, repository_id=repository_id, file_path=file_path, commit_sha=commit_sha)
