from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.approvals.policy import ACTION_CREATE_ISSUE
from app.workflows.publishing.nodes import PublishNodes
from app.workflows.publishing.state import PublishDeps, PublishState


def build_graph(deps: PublishDeps):
    nodes = PublishNodes(deps)
    g = StateGraph(PublishState)
    for name in ("preflight", "create_branch", "commit_file", "create_pull_request", "create_issue"):
        g.add_node(name, getattr(nodes, name))
    g.add_conditional_edges(
        START, lambda s: "create_issue" if deps.action_kind == ACTION_CREATE_ISSUE else "preflight",
        {"create_issue": "create_issue", "preflight": "preflight"},
    )
    g.add_edge("preflight", "create_branch")
    g.add_edge("create_branch", "commit_file")
    g.add_edge("commit_file", "create_pull_request")
    g.add_edge("create_pull_request", END)
    g.add_edge("create_issue", END)
    return g.compile()


async def run_publishing(deps: PublishDeps) -> list[dict[str, Any]]:
    """Execute the approved steps in order; each step verifies its own result before the next runs."""
    final = await build_graph(deps).ainvoke({"results": []})
    return list(final["results"])
