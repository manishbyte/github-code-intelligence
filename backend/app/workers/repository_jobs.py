"""Background repository analysis jobs."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.core.exceptions import GitHubNotConnectedError
from app.integrations.github.client import GitHubClient
from app.models.github_account import GitHubAccount
from app.tools import ToolContext
from app.workers.queue import ClaimedJob, WorkerContext
from app.workflows.common import WorkflowDeps
from app.workflows.repository_inspection.graph import run_repository_inspection


async def refresh_repository(ctx: WorkerContext, job: ClaimedJob) -> dict[str, Any]:
    """Re-inspect a repository using the owning user's stored GitHub token."""
    if job.user_id is None:
        raise GitHubNotConnectedError("The job has no owner.")
    async with ctx.session_factory() as db:
        account = (await db.execute(select(GitHubAccount).where(GitHubAccount.user_id == job.user_id))).scalar_one_or_none()
        if account is None:
            raise GitHubNotConnectedError("The user has no connected GitHub account.")
        client = GitHubClient(ctx.cipher.decrypt(account.encrypted_access_token), transport=ctx.transport)
        read_ctx = ToolContext(user_id=str(job.user_id), client=client, max_file_bytes=ctx.settings.max_source_file_bytes)
        deps = WorkflowDeps(db=db, user_id=job.user_id, read_ctx=read_ctx, settings=ctx.settings, github_account_id=account.id)
        state = await run_repository_inspection(deps, str(job.payload["repository_url"]))
        return {"repository_id": state["repository_id"], "snapshot_id": state.get("snapshot_id"), "commit_sha": state.get("head_sha")}


HANDLERS = {"repository_refresh": refresh_repository}
