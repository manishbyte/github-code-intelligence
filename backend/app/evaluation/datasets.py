"""Evaluation datasets: JSON files under ``evaluation_data/<kind-dir>/`` synced to PostgreSQL."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConfigurationError
from app.models.evaluation_case import EvaluationCase
from app.models.evaluation_dataset import EvaluationDataset

KIND_DIRS = {
    "tree": "repository_trees", "review": "code_review", "issue": "issue_decisions", "comment": "comment_generation",
    "logging": "logging_generation", "patch": "patch_validation", "safety": "security",
}
ALL_KINDS = tuple(KIND_DIRS)


@dataclass(frozen=True)
class Case:
    key: str
    input: dict[str, Any]
    expected: dict[str, Any]


@dataclass(frozen=True)
class Dataset:
    kind: str
    name: str
    version: str
    cases: tuple[Case, ...]


def data_root() -> Path:
    override = os.environ.get("EVALUATION_DATA_DIR")
    return Path(override) if override else Path(__file__).resolve().parents[3] / "evaluation_data"


def load_dataset(kind: str) -> Dataset:
    if kind not in KIND_DIRS:
        raise ConfigurationError(f"Unknown evaluation kind: {kind}")
    directory = data_root() / KIND_DIRS[kind]
    files = sorted(directory.glob("*.json")) if directory.is_dir() else []
    cases: list[Case] = []
    seen: set[str] = set()
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        for raw in data.get("cases", []):
            key = f"{path.stem}:{raw['key']}"
            if key in seen:
                raise ConfigurationError(f"Duplicate evaluation case key: {key}")
            seen.add(key)
            cases.append(Case(key=key, input=raw["input"], expected=raw["expected"]))
    digest = hashlib.sha256(json.dumps([(c.key, c.input, c.expected) for c in cases], sort_keys=True).encode()).hexdigest()
    return Dataset(kind=kind, name=KIND_DIRS[kind], version=digest, cases=tuple(cases))


async def sync_dataset(db: AsyncSession, dataset: Dataset) -> dict[str, uuid.UUID]:
    """Upsert the dataset version and its cases; returns case_key -> case id."""
    row = (await db.execute(select(EvaluationDataset).where(
        EvaluationDataset.kind == dataset.kind, EvaluationDataset.version == dataset.version))).scalar_one_or_none()
    if row is None:
        row = EvaluationDataset(kind=dataset.kind, name=dataset.name, version=dataset.version)
        db.add(row)
        await db.flush()
    existing = {c.case_key: c.id for c in (await db.execute(select(EvaluationCase).where(EvaluationCase.dataset_id == row.id))).scalars()}
    for case in dataset.cases:
        if case.key not in existing:
            c = EvaluationCase(dataset_id=row.id, case_key=case.key, input=case.input, expected=case.expected)
            db.add(c)
            await db.flush()
            existing[case.key] = c.id
    return existing
