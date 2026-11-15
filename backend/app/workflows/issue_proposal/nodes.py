from __future__ import annotations

import uuid

from sqlalchemy import select

from app.agents.issue_agent import IssueAgent
from app.approvals.decisions import create_approval
from app.approvals.policy import ACTION_CREATE_ISSUE
from app.core.exceptions import InvalidInputError
from app.core.permissions import ensure_owner
from app.guardrails.action_policy import payload_digest
from app.guardrails.secret_detection import find_secrets
from app.integrations.github.exceptions import GitHubError
from app.integrations.github.issues import list_open_issues
from app.models.analysis_run import AnalysisRun
from app.models.generated_artifact import GeneratedArtifact
from app.models.review_finding import ReviewFinding
from app.tools.github_write import create_issue
from app.workflows.common import WorkflowDeps, load_repository
from app.workflows.issue_proposal.state import IssueState
from app.workflows.issue_proposal.validators import (
    compose_issue_body, find_duplicates, select_findings, validate_issue_draft,
)


class IssueNodes:
    def __init__(self, deps: WorkflowDeps, agent: IssueAgent) -> None:
        self.d, self.agent = deps, agent

    async def load(self, state: IssueState) -> IssueState:
        run = (await self.d.db.execute(select(AnalysisRun).where(AnalysisRun.id == uuid.UUID(state["analysis_id"])))).scalar_one_or_none()
        run = ensure_owner(run, self.d.user_id, "Review")
        if run.kind != "review" or run.status != "succeeded" or run.decision != "issue" or run.repository_id is None:
            raise InvalidInputError("Only completed reviews with validated findings can become an issue proposal.")
        repo = await load_repository(self.d.db, self.d.user_id, run.repository_id)
        rows = (await self.d.db.execute(select(ReviewFinding).where(
            ReviewFinding.analysis_run_id == run.id, ReviewFinding.user_id == self.d.user_id, ReviewFinding.validated.is_(True)
        ))).scalars().all()
        chosen = select_findings(rows, state.get("finding_ids"))
        if not chosen:
            raise InvalidInputError("There are no validated findings to report.")
        findings = [{"id": str(r.id), "title": r.title, "severity": r.severity, "category": r.category,
                     "confidence": r.confidence, "description": r.description, "start_line": r.start_line,
                     "end_line": r.end_line, "evidence": r.evidence} for r in chosen]
        return {"run": run, "repo": repo, "findings": findings, "warnings": []}

    async def draft(self, state: IssueState) -> IssueState:
        repo, run = state["repo"], state["run"]
        draft, _ = await self.agent.draft(repo_full_name=f"{repo.owner}/{repo.name}", file_path=run.file_path or "",
                                          findings=state["findings"])
        return {"draft": validate_issue_draft(draft)}

    async def check_duplicates(self, state: IssueState) -> IssueState:
        repo, draft = state["repo"], state["draft"]
        try:
            open_issues = await list_open_issues(self.d.read_ctx.client, repo.owner, repo.name)
        except GitHubError:
            return {"duplicates": [], "warnings": [*state["warnings"], "Duplicate check was unavailable."]}
        return {"duplicates": find_duplicates(draft.title, [(i.number, i.title, i.html_url) for i in open_issues])}

    async def persist(self, state: IssueState) -> IssueState:
        repo, run, draft = state["repo"], state["run"], state["draft"]
        body = compose_issue_body(draft, state["findings"], file_path=run.file_path or "", html_url=repo.html_url, commit_sha=run.commit_sha or "")
        if find_secrets(draft.title + "\n" + body):
            raise InvalidInputError("The proposed issue contains what looks like a credential.")
        params = create_issue.CreateIssueInput(owner=repo.owner, repo=repo.name, title=draft.title, body=body, labels=[])
        payload = create_issue.build_payload(params)
        artifact = GeneratedArtifact(
            analysis_run_id=run.id, user_id=self.d.user_id, kind="issue_proposal",
            payload={"issue": payload, "duplicates": state["duplicates"], "finding_ids": [f["id"] for f in state["findings"]],
                     "warnings": state["warnings"]},
            payload_digest=payload_digest(payload),
        )
        self.d.db.add(artifact)
        await self.d.db.flush()
        approval = await create_approval(
            self.d.db, approval_id=uuid.uuid4(), user_id=self.d.user_id, artifact_id=artifact.id,
            action_type=ACTION_CREATE_ISSUE, owner=repo.owner, repo=repo.name, payload=payload, now=self.d.now(),
        )
        await self.d.db.commit()
        return {"payload": payload, "artifact_id": str(artifact.id), "approval_id": str(approval.id)}
