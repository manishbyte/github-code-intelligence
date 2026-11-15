"""Tool layer: the only code agents/workflows use to touch GitHub or analyze code.

GitHub MCP server tool -> project tool mapping (the MCP schemas define the
contract; the project calls the GitHub REST API through ``integrations/github``):

* ``get_me``                          -> ``github_read.get_user_profile``
* ``get_file_contents`` (ref/sha)     -> ``github_read.get_file_content`` (commit-SHA pinned)
* ``get_repository_tree``             -> ``github_read.get_repository_tree`` (truncation resolved)
* repo metadata/permissions           -> ``github_read.get_repository`` / ``check_permissions``
  (MCP ``list_repository_collaborators`` needs push access, so ``permissions``
  from ``GET /repos/{owner}/{repo}`` is used instead)
* ``issue_write(method=create)``      -> ``github_write.create_issue``
* ``create_branch``                   -> ``github_write.create_branch`` (pinned ``from_sha``)
* ``create_or_update_file``           -> ``github_write.create_commit`` (update only; ``sha`` mandatory)
* ``create_pull_request``             -> ``github_write.create_pull_request``

Deliberately NOT ported: ``delete_file``, ``merge_pull_request``, ``push_files``,
``update_pull_request*``, ``create_repository``, ``fork_repository`` and review tools.

Write tools are never registered for agents; only the publishing component
calls them, with an ``ApprovedAction`` issued by the approvals state machine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from app.core.constants import DEFAULT_MAX_SOURCE_FILE_BYTES, MAX_TREE_ENTRIES
from app.guardrails.action_policy import ActionLedger
from app.integrations.github.client import GitHubClient


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ToolContext:
    """Per-request context for read tools. ``client`` is bound to this user's token."""

    user_id: str
    client: GitHubClient
    max_file_bytes: int = DEFAULT_MAX_SOURCE_FILE_BYTES
    max_tree_entries: int = MAX_TREE_ENTRIES

    def __post_init__(self) -> None:
        if not self.user_id:
            raise ValueError("user_id is required")
        if self.client.allow_writes:
            raise ValueError("Read tools must not receive a write-enabled GitHub client.")


@dataclass(frozen=True)
class WriteToolContext:
    """Context for the publishing component only."""

    user_id: str
    client: GitHubClient  # allow_writes=True
    ledger: ActionLedger
    max_file_bytes: int = DEFAULT_MAX_SOURCE_FILE_BYTES
    now: Callable[[], datetime] = _utcnow

    def __post_init__(self) -> None:
        if not self.user_id:
            raise ValueError("user_id is required")
        if not self.client.allow_writes:
            raise ValueError("Write tools require a write-enabled GitHub client.")
