"""Complete repository tree retrieval (Git Trees API) with truncation handling."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

from app.core.constants import MAX_TREE_ENTRIES
from app.core.exceptions import InvalidInputError
from app.guardrails.path_safety import validate_repo_path
from app.integrations.github.client import GitHubClient, as_mapping
from app.integrations.github.exceptions import GitHubError

EntryKind = Literal["file", "directory", "symlink", "submodule"]


@dataclass(frozen=True)
class TreeEntryData:
    path: str
    kind: EntryKind
    sha: str
    mode: str
    size: int | None


@dataclass(frozen=True)
class CompleteTree:
    commit_sha: str
    tree_sha: str
    entries: tuple[TreeEntryData, ...]
    skipped_unsafe: int


def _kind(entry: Mapping[str, Any]) -> EntryKind | None:
    etype, mode = entry.get("type"), str(entry.get("mode", ""))
    if etype == "tree":
        return "directory"
    if etype == "commit":
        return "submodule"
    if etype == "blob":
        return "symlink" if mode == "120000" else "file"
    return None


def normalize_tree_entries(raw: Sequence[Mapping[str, Any]]) -> tuple[tuple[TreeEntryData, ...], int]:
    """Validate, de-duplicate and sort raw entries (directories first, then by path).

    Entries with unsafe paths or unknown types are skipped and counted, never invented.
    """
    seen: dict[str, TreeEntryData] = {}
    skipped = 0
    for item in raw:
        kind = _kind(item)
        path, sha = item.get("path"), item.get("sha")
        if kind is None or not isinstance(path, str) or not isinstance(sha, str):
            skipped += 1
            continue
        try:
            path = validate_repo_path(path)
        except InvalidInputError:
            skipped += 1
            continue
        size = item.get("size")
        seen[path] = TreeEntryData(path, kind, sha, str(item.get("mode", "")), size if isinstance(size, int) else None)
    ordered = sorted(seen.values(), key=lambda e: (e.path.split("/"), e.kind != "directory"))
    return tuple(ordered), skipped


async def fetch_complete_tree(
    client: GitHubClient,
    owner: str,
    repo: str,
    commit_sha: str,
    *,
    max_entries: int = MAX_TREE_ENTRIES,
    concurrency: int = 5,
) -> CompleteTree:
    commit = as_mapping((await client.request("GET", f"/repos/{owner}/{repo}/git/commits/{commit_sha}")).data, "commit")
    tree_obj = commit.get("tree")
    tree_sha = tree_obj.get("sha") if isinstance(tree_obj, dict) else None
    if not isinstance(tree_sha, str):
        raise GitHubError("Unexpected GitHub commit response.")

    sem = asyncio.Semaphore(concurrency)
    collected: list[Mapping[str, Any]] = []

    async def get_tree(sha: str, recursive: bool) -> Mapping[str, Any]:
        async with sem:
            params = {"recursive": "1"} if recursive else None
            resp = await client.request("GET", f"/repos/{owner}/{repo}/git/trees/{sha}", params=params)
        return as_mapping(resp.data, "tree")

    def add(prefix: str, items: Sequence[Mapping[str, Any]]) -> None:
        for item in items:
            collected.append({**item, "path": prefix + str(item.get("path", ""))})
        if len(collected) > max_entries:
            raise InvalidInputError("Repository tree is too large to inspect.")

    async def walk(sha: str, prefix: str) -> None:
        data = await get_tree(sha, recursive=True)
        items = data.get("tree")
        if not isinstance(items, list):
            raise GitHubError("Unexpected GitHub tree response.")
        if not data.get("truncated"):
            add(prefix, items)
            return
        flat = await get_tree(sha, recursive=False)
        level = flat.get("tree")
        if not isinstance(level, list) or flat.get("truncated"):
            raise InvalidInputError("Repository directory is too large to inspect.")
        add(prefix, level)
        subtrees = [e for e in level if e.get("type") == "tree"]
        await asyncio.gather(*(walk(str(e["sha"]), f"{prefix}{e['path']}/") for e in subtrees))

    await walk(tree_sha, "")
    entries, skipped = normalize_tree_entries(collected)
    return CompleteTree(commit_sha=commit_sha, tree_sha=tree_sha, entries=entries, skipped_unsafe=skipped)
