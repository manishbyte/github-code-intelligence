"""Executes an evaluation run: loads datasets, runs evaluators, stores results and metrics."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.evaluation_agent import EvaluationAgent
from app.agents.llm import GroqClient
from app.core.exceptions import AppError
from app.evaluation import regression
from app.evaluation.datasets import ALL_KINDS, Case, load_dataset, sync_dataset
from app.evaluation.evaluators.comment_evaluator import CommentEvaluator
from app.evaluation.evaluators.issue_evaluator import IssueEvaluator
from app.evaluation.evaluators.logging_evaluator import LoggingEvaluator
from app.evaluation.evaluators.patch_evaluator import PatchEvaluator
from app.evaluation.evaluators.review_evaluator import ReviewEvaluator
from app.evaluation.evaluators.safety_evaluator import SafetyEvaluator
from app.evaluation.evaluators.tree_evaluator import TreeEvaluator
from app.evaluation.judges.llm_judge import LLMJudge
from app.evaluation.metrics import CaseOutcome, aggregate, summarize
from app.models.evaluation_case_result import EvaluationCaseResult
from app.models.evaluation_run import EvaluationRun


def build_evaluator(kind: str, llm: GroqClient | None, judge: LLMJudge | None):
    return {
        "tree": lambda: TreeEvaluator(), "patch": lambda: PatchEvaluator(), "safety": lambda: SafetyEvaluator(),
        "issue": lambda: IssueEvaluator(), "review": lambda: ReviewEvaluator(llm, judge),
        "comment": lambda: CommentEvaluator(llm, judge), "logging": lambda: LoggingEvaluator(llm, judge),
    }[kind]()


async def run_evaluation(
    db: AsyncSession, run: EvaluationRun, *, llm_factory: Callable[[str | None], GroqClient | None],
    use_judge: bool = False, concurrency: int = 2,
) -> None:
    kinds = ALL_KINDS if run.kind == "all" else (run.kind,)
    llm = llm_factory(run.model)
    run.model = run.model or (llm.model if llm else None)
    run.status = "running"
    await db.commit()
    judge = LLMJudge(EvaluationAgent(llm)) if use_judge and llm else None
    by_kind: dict[str, dict] = {}
    try:
        for kind in kinds:
            dataset = load_dataset(kind)
            if not dataset.cases:
                continue
            ids = await sync_dataset(db, dataset)
            evaluator = build_evaluator(kind, llm, judge)
            sem = asyncio.Semaphore(concurrency)

            async def one(case: Case) -> CaseOutcome:
                async with sem:
                    started = time.perf_counter()
                    try:
                        outcome = await evaluator.evaluate(case)
                    except Exception as exc:  # a crashing case is an error, not a pass or a failure
                        msg = exc.message if isinstance(exc, AppError) else type(exc).__name__
                        outcome = CaseOutcome(False, 0.0, error=msg[:300])
                    if not outcome.latency_ms:
                        outcome.latency_ms = int((time.perf_counter() - started) * 1000)
                    return outcome

            outcomes = await asyncio.gather(*(one(c) for c in dataset.cases))
            for case, outcome in zip(dataset.cases, outcomes):
                db.add(EvaluationCaseResult(run_id=run.id, case_id=ids[case.key], kind=kind, passed=outcome.passed,
                                            score=outcome.score, latency_ms=outcome.latency_ms,
                                            details={**outcome.details, "error": outcome.error, "case_key": case.key}))
            by_kind[kind] = summarize(outcomes)
        run.metrics = {"by_kind": by_kind, "overall": aggregate(by_kind), "model": run.model}
        run.regression = await regression.compare_with_previous(db, run)
        run.status = "succeeded"
    except Exception as exc:
        await db.rollback()
        run.status = "failed"
        run.error = (exc.message if isinstance(exc, AppError) else type(exc).__name__)[:500]
    run.completed_at = datetime.now(timezone.utc)
    await db.commit()
