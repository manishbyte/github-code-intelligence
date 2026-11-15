"""Fetch one text file pinned to a commit. Content is untrusted repository data."""

from __future__ import annotations

from pydantic import Field

from app.guardrails.input_validation import validate_commit_sha, validate_owner_repo
from app.guardrails.path_safety import validate_repo_path
from app.guardrails.patch_safety import split_lines
from app.guardrails.secret_detection import find_secrets
from app.integrations.github.contents import get_file
from app.schemas.common import SecretFindingModel, StrictModel
from app.schemas.file import FileContent
from app.tools import ToolContext
from app.tools.code_analysis.detect_language import guess_language

TOOL_NAME = "get_file_content"

_MESSAGES = {
    "not_found": "The file does not exist at this commit.",
    "not_a_file": "The path is a directory, not a file.",
    "unsupported_type": "Symlinks and submodules are not supported.",
    "too_large": "The file exceeds the size limit and was not read.",
    "binary": "The file is binary or not valid UTF-8 and was not read.",
}


class GetFileContentInput(StrictModel):
    owner: str = Field(min_length=1, max_length=39)
    repo: str = Field(min_length=1, max_length=100)
    path: str = Field(min_length=1, max_length=1024)
    commit_sha: str = Field(min_length=40, max_length=64)


async def run(ctx: ToolContext, params: GetFileContentInput) -> FileContent:
    ref = validate_owner_repo(params.owner, params.repo)
    sha = validate_commit_sha(params.commit_sha)
    path = validate_repo_path(params.path)
    fetched = await get_file(ctx.client, ref.owner, ref.name, path, sha, max_bytes=ctx.max_file_bytes)

    def result(status: str, **kw: object) -> FileContent:
        base = dict(
            owner=ref.owner, repo=ref.name, path=path, commit_sha=sha, status=status,
            message=_MESSAGES.get(status), blob_sha=fetched.blob_sha, size_bytes=fetched.size,
            language=None, content=None, line_count=None, secret_findings=[],
        )
        base.update(kw)
        return FileContent(**base)  # type: ignore[arg-type]

    if fetched.status != "ok" or fetched.data is None:
        return result(fetched.status)
    try:
        text = fetched.data.decode("utf-8")
    except UnicodeDecodeError:
        return result("binary")
    if "\x00" in text:
        return result("binary")
    findings = [SecretFindingModel(rule=f.rule, line=f.line, preview=f.preview) for f in find_secrets(text)]
    first = text.split("\n", 1)[0]
    return result(
        "ok", content=text, line_count=len(split_lines(text)), secret_findings=findings,
        language=guess_language(path, first).language, message=None,
    )
