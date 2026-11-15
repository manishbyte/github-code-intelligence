"""File retrieval pinned to a commit SHA (read-only)."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

from app.guardrails.path_safety import validate_repo_path
from app.integrations.github.client import GitHubClient, as_mapping
from app.integrations.github.exceptions import GitHubError, GitHubNotFoundError

FileStatus = Literal["ok", "not_found", "not_a_file", "unsupported_type", "too_large"]


@dataclass(frozen=True)
class FileFetch:
    status: FileStatus
    path: str
    blob_sha: str | None = None
    size: int | None = None
    data: bytes | None = None


def _decode(b64: str) -> bytes:
    try:
        return base64.b64decode("".join(b64.split()), validate=True)
    except (binascii.Error, ValueError):
        raise GitHubError("GitHub returned invalid file encoding.") from None


async def get_file(
    client: GitHubClient, owner: str, repo: str, path: str, ref: str, *, max_bytes: int
) -> FileFetch:
    path = validate_repo_path(path)
    try:
        resp = await client.request(
            "GET", f"/repos/{owner}/{repo}/contents/{quote(path, safe='/')}", params={"ref": ref}
        )
    except GitHubNotFoundError:
        return FileFetch("not_found", path)
    if isinstance(resp.data, list):
        return FileFetch("not_a_file", path)
    data = as_mapping(resp.data, "contents")
    if data.get("type") != "file":
        return FileFetch("unsupported_type", path)
    size, sha = data.get("size"), data.get("sha")
    if not isinstance(size, int) or not isinstance(sha, str):
        raise GitHubError("Unexpected GitHub contents response.")
    if size > max_bytes:
        return FileFetch("too_large", path, sha, size)
    content = data.get("content")
    if data.get("encoding") == "base64" and isinstance(content, str) and (content or size == 0):
        raw = _decode(content)
    else:  # large files: contents API omits inline content
        blob = as_mapping((await client.request("GET", f"/repos/{owner}/{repo}/git/blobs/{sha}")).data, "blob")
        if blob.get("encoding") != "base64" or not isinstance(blob.get("content"), str):
            raise GitHubError("Unexpected GitHub blob response.")
        raw = _decode(blob["content"])
    if len(raw) != size:
        raise GitHubError("GitHub file size mismatch.")
    return FileFetch("ok", path, sha, size, raw)
