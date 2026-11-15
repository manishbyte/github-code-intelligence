from __future__ import annotations

import uuid

from langgraph.graph import END, START, StateGraph

from app.agents.issue_agent import IssueAgent
from app.workflows.common import WorkflowDeps
from app.workflows.issue_proposal.nodes import IssueNodes
from app.workflows.issue_proposal.state import IssueState


def build_graph(deps: WorkflowDeps):
    nodes = IssueNodes(deps, IssueAgent(deps.require_llm()))
    g = StateGraph(IssueState)
    # node names must differ from state keys (the state has a "draft" key)
    g.add_node("load", nodes.load)
    g.add_node("write_draft", nodes.draft)
    g.add_node("check_duplicates", nodes.check_duplicates)
    g.add_node("persist", nodes.persist)
    g.add_edge(START, "load")
    g.add_edge("load", "write_draft")
    g.add_edge("write_draft", "check_duplicates")
    g.add_edge("check_duplicates", "persist")
    g.add_edge("persist", END)
    return g.compile()


async def run_issue_proposal(deps: WorkflowDeps, *, analysis_id: uuid.UUID, finding_ids: list[uuid.UUID] | None) -> IssueState:
    try:
        return await build_graph(deps).ainvoke({"analysis_id": str(analysis_id), "finding_ids": [str(i) for i in finding_ids] if finding_ids else None})
    except Exception:
        await deps.db.rollback()
        raise
