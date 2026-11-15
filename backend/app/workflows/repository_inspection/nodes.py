from __future__ import annotations

import uuid
from dataclasses import asdict

from sqlalchemy import select

from app.authorization.workspace_access import get_personal_workspace
from app.guardrails.input_validation import parse_github_repo_url
from app.integrations.github.repositories import get_branch_head_sha, get_repository
from app.integrations.github.trees import fetch_complete_tree
from app.models.github_repository import GitHubRepository
from app.models.repository_snapshot import RepositorySnapshot
from app.workflows.common import WorkflowDeps
from app.workflows.repository_inspection.state import InspectionState
from app.workflows.repository_inspection.validators import validate_public_repository, validate_tree


class InspectionNodes:
    def __init__(self, deps: WorkflowDeps) -> None:
        self.d = deps

    async def fetch_repository(self, state: InspectionState) -> InspectionState:
        ref = parse_github_repo_url(state["url"])
        client = self.d.read_ctx.client
        repo = await get_repository(client, ref.owner, ref.name)
        validate_public_repository(repo)
        head = await get_branch_head_sha(client, repo.owner, repo.name, repo.default_branch)
        row = (await self.d.db.execute(select(GitHubRepository).where(
            GitHubRepository.user_id == self.d.user_id, GitHubRepository.owner == repo.owner, GitHubRepository.name == repo.name,
        ))).scalar_one_or_none()
        if row is None:
            workspace = await get_personal_workspace(self.d.db, self.d.user_id)
            row = GitHubRepository(user_id=self.d.user_id, workspace_id=workspace.id, owner=repo.owner, name=repo.name,
                                   html_url=repo.html_url, default_branch=repo.default_branch, visibility=repo.visibility,
                                   description=repo.description, connected_github_account_id=self.d.github_account_id)
            self.d.db.add(row)
        row.html_url, row.default_branch, row.visibility, row.description = repo.html_url, repo.default_branch, repo.visibility, repo.description
        await self.d.db.flush()
        return {"repo": repo, "head_sha": head, "repository_id": str(row.id), "is_empty": head is None, "snapshot_id": None, "entry_count": 0}

    async def load_tree(self, state: InspectionState) -> InspectionState:
        repo, head = state["repo"], state["head_sha"]
        repository_id = uuid.UUID(state["repository_id"])
        existing = (await self.d.db.execute(select(RepositorySnapshot).where(
            RepositorySnapshot.repository_id == repository_id, RepositorySnapshot.commit_sha == head,
            RepositorySnapshot.user_id == self.d.user_id,
        ))).scalar_one_or_none()
        if existing is not None:  # commit-SHA-keyed cache hit
            return {"snapshot_id": str(existing.id), "entry_count": existing.entry_count}
        tree = await fetch_complete_tree(self.d.read_ctx.client, repo.owner, repo.name, head,
                                         max_entries=self.d.read_ctx.max_tree_entries)
        validate_tree(tree, max_entries=self.d.read_ctx.max_tree_entries)
        snap = RepositorySnapshot(
            repository_id=repository_id, user_id=self.d.user_id, branch=repo.default_branch, commit_sha=head,
            tree_sha=tree.tree_sha, entry_count=len(tree.entries), skipped_unsafe_entries=tree.skipped_unsafe,
            tree=[asdict(e) for e in tree.entries],
        )
        self.d.db.add(snap)
        await self.d.db.flush()
        return {"snapshot_id": str(snap.id), "entry_count": snap.entry_count}

    async def finish(self, state: InspectionState) -> InspectionState:
        row = (await self.d.db.execute(select(GitHubRepository).where(GitHubRepository.id == uuid.UUID(state["repository_id"])))).scalar_one()
        row.last_inspected_at = self.d.now()
        await self.d.db.commit()
        return {}
