"""Deterministic validation of repository URLs, names, refs and SHAs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.constants import GITHUB_WEB_HOST
from app.core.exceptions import InvalidInputError

_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_BRANCH_SAFE_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
_MAX_URL_LENGTH = 300
_MAX_BRANCH_LENGTH = 200


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def html_url(self) -> str:
        return f"https://{GITHUB_WEB_HOST}/{self.owner}/{self.name}"


def validate_owner_repo(owner: str, repo: str) -> RepoRef:
    if not isinstance(owner, str) or not _OWNER_RE.fullmatch(owner) or "--" in owner:
        raise InvalidInputError("Invalid repository owner.")
    if (
        not isinstance(repo, str)
        or not _REPO_RE.fullmatch(repo)
        or repo in {".", ".."}
        or repo.lower().endswith(".git")
    ):
        raise InvalidInputError("Invalid repository name.")
    return RepoRef(owner=owner, name=repo)


def parse_github_repo_url(raw: str) -> RepoRef:
    """Parse ``https://github.com/<owner>/<repo>`` (optional ``.git``/trailing slash).

    Rejects other hosts, ports, credentials, queries, fragments, encoded
    characters, local paths and deep links (``/tree/...``) in this iteration.
    """
    if not isinstance(raw, str):
        raise InvalidInputError("Repository URL must be a string.")
    text = raw.strip()
    if not text or len(text) > _MAX_URL_LENGTH:
        raise InvalidInputError("Repository URL is empty or too long.")
    if any(ord(ch) < 32 or ord(ch) == 127 or ch in "\\ " for ch in text):
        raise InvalidInputError("Repository URL contains forbidden characters.")
    try:
        parts = urlsplit(text)
        hostname = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise InvalidInputError("Repository URL is malformed.") from exc
    if parts.scheme != "https":
        raise InvalidInputError("Repository URL must use https.")
    if hostname is None or hostname.lower() != GITHUB_WEB_HOST:
        raise InvalidInputError("Only github.com repository URLs are supported.")
    if parts.username or parts.password or port is not None or "@" in parts.netloc:
        raise InvalidInputError("Repository URL must not contain credentials or a port.")
    if parts.query or parts.fragment or "%" in parts.path:
        raise InvalidInputError("Unsupported repository URL form.")
    stripped = parts.path.strip("/")
    segments = stripped.split("/") if stripped else []
    if len(segments) != 2 or parts.path.endswith("//"):
        raise InvalidInputError("URL must be of the form https://github.com/<owner>/<repo>.")
    owner, repo = segments
    if repo.lower().endswith(".git"):
        repo = repo[: -len(".git")]
    return validate_owner_repo(owner, repo)


def validate_commit_sha(sha: str) -> str:
    if not isinstance(sha, str) or not _SHA_RE.fullmatch(sha):
        raise InvalidInputError("A full lowercase hexadecimal commit SHA is required.")
    return sha


def validate_branch_name(name: str) -> str:
    """Validate a branch name using a strict subset of ``git check-ref-format``."""
    if not isinstance(name, str) or not name or len(name) > _MAX_BRANCH_LENGTH:
        raise InvalidInputError("Invalid branch name.")
    if not _BRANCH_SAFE_RE.fullmatch(name):
        raise InvalidInputError("Branch name contains unsupported characters.")
    if name.startswith(("-", "/")) or name.endswith(("/", ".")) or "//" in name or ".." in name:
        raise InvalidInputError("Invalid branch name.")
    for component in name.split("/"):
        if component.startswith(".") or component.endswith(".lock"):
            raise InvalidInputError("Invalid branch name.")
    return name
