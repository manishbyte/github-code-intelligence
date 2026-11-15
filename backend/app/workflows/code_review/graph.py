from __future__ import annotations

import uuid

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.agents.review_agent import ReviewAgent
from app.core.exceptions import AppError
from app.models.analysis_run import AnalysisRun
from app.workflows.code_review.nodes import ReviewNodes
from app.workflows.code_review.state import ReviewState
from app.workflows.common import WorkflowDeps


def build_graph(deps: WorkflowDeps, nodes: ReviewNodes | None = None):
    nodes = nodes or ReviewNodes(deps, ReviewAgent(deps.require_llm()))
    g = StateGraph(ReviewState)
    for name in ("load_file", "prepare", "call_model", "validate", "persist"):
        g.add_node(name, getattr(nodes, name))
    g.add_edge(START, "load_file")
    g.add_edge("load_file", "prepare")
    g.add_edge("prepare", "call_model")
    g.add_edge("call_model", "validate")
    g.add_edge("validate", "persist")
    g.add_edge("persist", END)
    return g.compile()


async def run_code_review(deps: WorkflowDeps, *, repository_id: uuid.UUID, file_path: str, commit_sha: str | None) -> uuid.UUID:
    """Run the review; on failure the analysis run (if created) is marked failed. Returns the run id."""
    nodes = ReviewNodes(deps, ReviewAgent(deps.require_llm()))
    graph = build_graph(deps, nodes)
    state: ReviewState = {"repository_id": str(repository_id), "file_path": file_path, "commit_sha": commit_sha}
    try:
        final = await graph.ainvoke(state)
        return uuid.UUID(final["run_id"])
    except Exception as exc:
        await deps.db.rollback()
        run = None
        if nodes.run_id is not None:
            run = (await deps.db.execute(
                select(AnalysisRun).where(AnalysisRun.id == nodes.run_id, AnalysisRun.user_id == deps.user_id)
            )).scalar_one_or_none()
        if run is not None:
            run.status, run.completed_at = "failed", deps.now()
            run.error = exc.message if isinstance(exc, AppError) else "Internal error during review."
            await deps.db.commit()
        raise
