from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.workflows.common import WorkflowDeps
from app.workflows.repository_inspection.nodes import InspectionNodes
from app.workflows.repository_inspection.state import InspectionState


def build_graph(deps: WorkflowDeps):
    nodes = InspectionNodes(deps)
    g = StateGraph(InspectionState)
    g.add_node("fetch_repository", nodes.fetch_repository)
    g.add_node("load_tree", nodes.load_tree)
    g.add_node("finish", nodes.finish)
    g.add_edge(START, "fetch_repository")
    g.add_conditional_edges(
        "fetch_repository", lambda s: "finish" if s.get("is_empty") else "load_tree",
        {"finish": "finish", "load_tree": "load_tree"},
    )
    g.add_edge("load_tree", "finish")
    g.add_edge("finish", END)
    return g.compile()


async def run_repository_inspection(deps: WorkflowDeps, repository_url: str) -> InspectionState:
    try:
        return await build_graph(deps).ainvoke({"url": repository_url})
    except Exception:
        await deps.db.rollback()
        raise
