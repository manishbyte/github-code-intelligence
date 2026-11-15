"""Return the complete, normalized file tree for a commit."""

from __future__ import annotations

from pydantic import Field

from app.guardrails.input_validation import validate_commit_sha, validate_owner_repo
from app.guardrails.path_safety import validate_repo_path
from app.integrations.github.trees import fetch_complete_tree
from app.schemas.common import StrictModel
from app.schemas.tree import RepositoryTree, TreeEntry
from app.tools import ToolContext

TOOL_NAME = "get_repository_tree"


class GetRepositoryTreeInput(StrictModel):
    owner: str = Field(min_length=1, max_length=39)
    repo: str = Field(min_length=1, max_length=100)
    commit_sha: str = Field(min_length=40, max_length=64)
    path_filter: str | None = Field(default=None, max_length=1024)


async def run(ctx: ToolContext, params: GetRepositoryTreeInput) -> RepositoryTree:
    ref = validate_owner_repo(params.owner, params.repo)
    sha = validate_commit_sha(params.commit_sha)
    prefix = validate_repo_path(params.path_filter, allow_trailing_slash=True) if params.path_filter else None
    tree = await fetch_complete_tree(ctx.client, ref.owner, ref.name, sha, max_entries=ctx.max_tree_entries)
    items = [
        e for e in tree.entries if prefix is None or e.path == prefix or e.path.startswith(prefix + "/")
    ]
    entries = [TreeEntry(path=e.path, kind=e.kind, sha=e.sha, mode=e.mode, size=e.size) for e in items]
    return RepositoryTree(
        owner=ref.owner, repo=ref.name, commit_sha=sha, tree_sha=tree.tree_sha, entries=entries,
        entry_count=len(entries),
        file_count=sum(1 for e in entries if e.kind == "file"),
        directory_count=sum(1 for e in entries if e.kind == "directory"),
        skipped_unsafe_entries=tree.skipped_unsafe, path_filter=prefix,
    )
