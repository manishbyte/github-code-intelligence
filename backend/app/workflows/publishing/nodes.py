from __future__ import annotations

import dataclasses
from typing import Any

from app.approvals.policy import step_payloads
from app.guardrails.action_policy import ApprovedAction, WriteActionType, payload_digest
from app.tools.github_write import create_branch, create_commit, create_issue, create_pull_request
from app.workflows.publishing.state import PublishDeps, PublishState
from app.workflows.publishing.validators import preflight_code_change

_STEP_TYPES = {
    "create_issue": WriteActionType.CREATE_ISSUE,
    "create_branch": WriteActionType.CREATE_BRANCH,
    "commit_file": WriteActionType.COMMIT_FILE,
    "create_pull_request": WriteActionType.CREATE_PULL_REQUEST,
}


class PublishNodes:
    def __init__(self, deps: PublishDeps) -> None:
        self.d = deps
        self._payloads = step_payloads(deps.action_kind, deps.approval_payload)

    def _action(self, step: str) -> ApprovedAction:
        """Derive the per-step capability: bound to this step's approved payload and idempotency key."""
        return dataclasses.replace(
            self.d.base, action_type=_STEP_TYPES[step], payload_digest=payload_digest(self._payloads[step]),
            idempotency_key=f"{self.d.base.approval_id}:{step}",
        )

    @staticmethod
    def _append(state: PublishState, result: Any) -> PublishState:
        return {"results": [*state.get("results", []), result.model_dump(mode="json")]}

    async def preflight(self, state: PublishState) -> PublishState:
        await preflight_code_change(self.d.ctx.client, self.d.approval_payload, self.d.artifact_payload,
                                    max_bytes=self.d.ctx.max_file_bytes)
        return {}

    async def create_branch(self, state: PublishState) -> PublishState:
        params = create_branch.CreateBranchInput(**self._payloads["create_branch"])
        return self._append(state, await create_branch.run(self.d.ctx, self._action("create_branch"), params))

    async def commit_file(self, state: PublishState) -> PublishState:
        p = self._payloads["commit_file"]
        params = create_commit.CreateCommitInput(
            owner=p["owner"], repo=p["repo"], branch=p["branch"], path=p["path"],
            content=self.d.artifact_payload["new_content"], message=p["message"], sha=p["sha"])
        return self._append(state, await create_commit.run(self.d.ctx, self._action("commit_file"), params))

    async def create_pull_request(self, state: PublishState) -> PublishState:
        params = create_pull_request.CreatePullRequestInput(**self._payloads["create_pull_request"])
        return self._append(state, await create_pull_request.run(self.d.ctx, self._action("create_pull_request"), params))

    async def create_issue(self, state: PublishState) -> PublishState:
        params = create_issue.CreateIssueInput(**self._payloads["create_issue"])
        return self._append(state, await create_issue.run(self.d.ctx, self._action("create_issue"), params))
