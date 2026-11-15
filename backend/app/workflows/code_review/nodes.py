from __future__ import annotations

import uuid

from sqlalchemy import select

from app.agents.review_agent import ReviewAgent
from app.core.exceptions import InvalidInputError
from app.guardrails.prompt_injection import scan_for_injection
from app.guardrails.secret_detection import find_secrets, redact_secrets
from app.models.analysis_run import AnalysisRun
from app.models.review_finding import ReviewFinding
from app.tools.code_analysis.detect_language import guess_language
from app.workflows.code_review import prompts
from app.workflows.code_review.state import ReviewState
from app.workflows.code_review.validators import validate_review
from app.workflows.common import WorkflowDeps, load_file, load_repository, resolve_snapshot


class ReviewNodes:
    def __init__(self, deps: WorkflowDeps, agent: ReviewAgent) -> None:
        self.d, self.agent = deps, agent
        self.run_id: uuid.UUID | None = None

    async def load_file(self, state: ReviewState) -> ReviewState:
        repo = await load_repository(self.d.db, self.d.user_id, uuid.UUID(state["repository_id"]))
        snap = await resolve_snapshot(self.d.db, self.d.user_id, repo, state.get("commit_sha"))
        f = await load_file(self.d, repo, snap, state["file_path"])
        run = AnalysisRun(user_id=self.d.user_id, repository_id=repo.id, snapshot_id=snap.id, kind="review",
                          status="running", file_path=f.path, commit_sha=snap.commit_sha, model=self.d.llm.model if self.d.llm else None)
        self.d.db.add(run)
        await self.d.db.commit()
        self.run_id = run.id
        return {"run_id": str(run.id), "content": f.content, "language": f.language, "file_path": f.path, "commit_sha": snap.commit_sha}

    async def prepare(self, state: ReviewState) -> ReviewState:
        content = state["content"]
        if len(content) // 4 > self.d.settings.max_review_input_tokens:
            raise InvalidInputError("This file is too large to review within the configured token budget.")
        warnings: list[str] = []
        injections = scan_for_injection(content)
        if injections:
            warnings.append(prompts.injection_warning(sorted({i.line for i in injections})))
        secrets = find_secrets(content)
        if secrets:
            warnings.append(prompts.secret_warning(len(secrets)))
        return {"redacted": redact_secrets(content), "warnings": warnings, "secret_findings": secrets,
                "language": state.get("language") or guess_language(state["file_path"]).language}

    async def call_model(self, state: ReviewState) -> ReviewState:
        raw, result = await self.agent.review(file_path=state["file_path"], language=state.get("language"),
                                              content=state["redacted"], warnings=state["warnings"])
        return {"raw": raw, "usage": result.usage, "latency_ms": result.latency_ms}

    async def validate(self, state: ReviewState) -> ReviewState:
        return {"validated": validate_review(state["raw"], content=state["redacted"], secret_findings=state["secret_findings"])}

    async def persist(self, state: ReviewState) -> ReviewState:
        run = (await self.d.db.execute(select(AnalysisRun).where(AnalysisRun.id == uuid.UUID(state["run_id"])))).scalar_one()
        v = state["validated"]
        run.status, run.decision, run.reasoning = "succeeded", v.decision, v.reasoning
        run.warnings = list(state["warnings"]) + [f"Rejected: {r}" for r in v.rejected[:10]]
        run.token_usage, run.latency_ms, run.completed_at = state.get("usage"), state.get("latency_ms"), self.d.now()
        for f in v.findings:
            self.d.db.add(ReviewFinding(
                analysis_run_id=run.id, user_id=self.d.user_id, category=f.category, severity=f.severity,
                confidence=f.confidence, title=f.title, description=f.description, start_line=f.start_line,
                end_line=f.end_line, evidence=f.evidence, suggested_fix=f.suggested_fix, validated=True))
        await self.d.db.commit()
        return {}
