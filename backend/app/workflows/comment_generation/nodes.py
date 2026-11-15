"""Shared pipeline for comment and logging proposals (subclasses supply conventions and validation)."""

from __future__ import annotations

import uuid
from types import ModuleType
from typing import Any

from sqlalchemy import select

from app.agents.patch_agent import PatchAgent, ValidEdit, detect_comment_conventions, validate_comment_edits
from app.approvals.decisions import create_approval
from app.approvals.policy import ACTION_CODE_CHANGE
from app.core.exceptions import InvalidInputError
from app.guardrails.action_policy import payload_digest
from app.guardrails.patch_safety import validate_single_file_patch
from app.guardrails.prompt_injection import scan_for_injection
from app.guardrails.secret_detection import redact_secrets
from app.models.analysis_run import AnalysisRun
from app.models.generated_artifact import GeneratedArtifact
from app.schemas.code_change import RawEdits
from app.tools.code_analysis.detect_language import guess_language
from app.tools.code_analysis.run_quality_checks import RunQualityChecksInput, run as run_quality_checks
from app.workflows.code_review.prompts import injection_warning
from app.workflows.comment_generation import prompts as comment_prompts
from app.workflows.comment_generation.state import CodeChangeState
from app.workflows.common import WorkflowDeps, load_file, load_repository, resolve_snapshot
from app.workflows.publishing.validators import build_code_change_payload


class CodeChangeNodes:
    """Pipeline: load_file -> inspect -> generate -> build_patch -> persist."""

    prompts: ModuleType = comment_prompts

    def __init__(self, deps: WorkflowDeps, agent: Any) -> None:
        self.d, self.agent = deps, agent
        self.run_id: uuid.UUID | None = None

    # ---- hooks -------------------------------------------------------
    def _conventions(self, language: str, content: str) -> dict[str, Any]:
        return detect_comment_conventions(language, content)

    async def _propose(self, state: CodeChangeState):  # -> (RawEdits, LLMResult)
        return await self.agent.propose(file_path=state["file_path"], language=state["language"],
                                        content=state["redacted"], conventions=state["conventions"])

    def _validate(self, language: str, content: str, raw: RawEdits, conventions: dict[str, Any]) -> tuple[list[ValidEdit], list[str]]:
        return validate_comment_edits(language, content, raw.edits)

    # ---- nodes -------------------------------------------------------
    async def load_file(self, state: CodeChangeState) -> CodeChangeState:
        repo = await load_repository(self.d.db, self.d.user_id, uuid.UUID(state["repository_id"]))
        snap = await resolve_snapshot(self.d.db, self.d.user_id, repo, state.get("commit_sha"))
        f = await load_file(self.d, repo, snap, state["file_path"])
        run = AnalysisRun(user_id=self.d.user_id, repository_id=repo.id, snapshot_id=snap.id, kind=self.prompts.KIND,
                          status="running", file_path=f.path, commit_sha=snap.commit_sha,
                          model=self.d.llm.model if self.d.llm else None)
        self.d.db.add(run)
        await self.d.db.commit()
        self.run_id = run.id
        return {"run_id": str(run.id), "content": f.content, "blob_sha": f.blob_sha, "file_path": f.path,
                "commit_sha": snap.commit_sha, "owner": repo.owner, "repo_name": repo.name,
                "default_branch": repo.default_branch, "language": f.language}

    async def inspect(self, state: CodeChangeState) -> CodeChangeState:
        content = state["content"]
        language = state.get("language") or guess_language(state["file_path"]).language
        if not language:
            raise InvalidInputError("The language of this file could not be determined.")
        if len(content) // 4 > self.d.settings.max_review_input_tokens:
            raise InvalidInputError("This file is too large for generation within the configured token budget.")
        warnings: list[str] = []
        injections = scan_for_injection(content)
        if injections:
            warnings.append(injection_warning(sorted({i.line for i in injections})))
        return {"language": language, "conventions": self._conventions(language, content),
                "redacted": redact_secrets(content), "warnings": warnings}

    async def generate(self, state: CodeChangeState) -> CodeChangeState:
        raw, result = await self._propose(state)
        return {"raw": raw, "usage": result.usage, "latency_ms": result.latency_ms}

    async def build_patch(self, state: CodeChangeState) -> CodeChangeState:
        path, content = state["file_path"], state["content"]
        edits, dropped = self._validate(state["language"], content, state["raw"], state["conventions"])
        built = PatchAgent.build(path, content, edits, dropped)
        validation = validate_single_file_patch(built.diff, expected_path=path, original_content=content,
                                                max_bytes=self.d.read_ctx.max_file_bytes)
        if validation.patched_content != built.new_content:
            raise InvalidInputError("The generated patch failed its consistency check.")
        if not validation.safe:
            raise InvalidInputError("The generated change adds content that looks like a credential.")
        quality = run_quality_checks(RunQualityChecksInput(path=path, original_content=content, patched_content=built.new_content,
                                                           max_bytes=self.d.read_ctx.max_file_bytes))
        if not quality.passed:
            failed = ", ".join(c.name for c in quality.checks if c.status == "failed")
            raise InvalidInputError(f"The generated change failed automated quality checks: {failed}.")
        return {"patch": built, "quality": quality, "dropped": list(dropped)}

    async def persist(self, state: CodeChangeState) -> CodeChangeState:
        built, quality, raw = state["patch"], state["quality"], state["raw"]
        approval_id = uuid.uuid4()
        summary = raw.summary.strip()[:300]
        path = state["file_path"]
        approval_payload = build_code_change_payload(
            owner=state["owner"], repo=state["repo_name"], default_branch=state["default_branch"],
            base_commit_sha=state["commit_sha"], base_blob_sha=state["blob_sha"], path=path,
            new_content=built.new_content, approval_id=approval_id, branch_slug=self.prompts.SLUG,
            commit_message=self.prompts.commit_message(path, summary), pr_title=self.prompts.pr_title(path),
            pr_body=self.prompts.pr_body(path, summary, built.applied_edits),
        )
        artifact_payload = {
            "path": path, "kind": self.prompts.ARTIFACT_KIND, "summary": summary, "diff": built.diff,
            "new_content": built.new_content, "base_commit_sha": state["commit_sha"], "base_blob_sha": state["blob_sha"],
            "quality": quality.model_dump(mode="json"), "dropped": list(state.get("dropped", [])),
            "warnings": state["warnings"], "owner": state["owner"], "repo": state["repo_name"],
        }
        artifact = GeneratedArtifact(analysis_run_id=uuid.UUID(state["run_id"]), user_id=self.d.user_id,
                                     kind=self.prompts.ARTIFACT_KIND, payload=artifact_payload,
                                     payload_digest=payload_digest(artifact_payload))
        self.d.db.add(artifact)
        await self.d.db.flush()
        approval = await create_approval(
            self.d.db, approval_id=approval_id, user_id=self.d.user_id, artifact_id=artifact.id,
            action_type=ACTION_CODE_CHANGE, owner=state["owner"], repo=state["repo_name"], payload=approval_payload, now=self.d.now(),
        )
        run = (await self.d.db.execute(select(AnalysisRun).where(AnalysisRun.id == uuid.UUID(state["run_id"])))).scalar_one()
        run.status, run.decision, run.reasoning = "succeeded", "proposal", summary
        run.warnings = list(state["warnings"]) + [f"Dropped: {d}" for d in state.get("dropped", [])[:10]]
        run.token_usage, run.latency_ms, run.completed_at = state.get("usage"), state.get("latency_ms"), self.d.now()
        await self.d.db.commit()
        return {"artifact_id": str(artifact.id), "approval_id": str(approval.id), "payload": approval_payload}
