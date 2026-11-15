from __future__ import annotations

from app.core.exceptions import InvalidInputError
from app.integrations.github.repositories import RepositoryData
from app.integrations.github.trees import CompleteTree


def validate_public_repository(repo: RepositoryData) -> None:
    if repo.visibility != "public":
        raise InvalidInputError("Only public repositories are supported.")
    if repo.disabled:
        raise InvalidInputError("This repository is disabled on GitHub.")


def validate_tree(tree: CompleteTree, *, max_entries: int) -> None:
    if len(tree.entries) > max_entries:
        raise InvalidInputError("Repository tree is too large to inspect.")
    if any(e.path.startswith("/") or ".." in e.path.split("/") for e in tree.entries):
        raise InvalidInputError("Repository tree contains unsafe paths.")
