"""GitHub write tools. NOT for agents: only the publishing component may call them,
and only with an ``ApprovedAction`` produced by the human-approval state machine."""

from app.tools.github_write import create_branch, create_commit, create_issue, create_pull_request

WRITE_TOOLS = {
    m.TOOL_NAME: m for m in (create_branch, create_commit, create_issue, create_pull_request)
}
