"""Strict single-file unified-diff parsing, application and safety validation.

No fuzz: every context and removed line must match the original exactly, so a
patch generated against an older version fails instead of silently applying.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.constants import DEFAULT_MAX_SOURCE_FILE_BYTES, MAX_PATCH_BYTES
from app.core.exceptions import PatchApplyError, PatchSafetyError
from app.guardrails.path_safety import validate_repo_path, validate_write_path
from app.guardrails.secret_detection import SecretFinding, find_secrets_in_added_lines

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_LINE_RE = re.compile(r"[^\n]*\n|[^\n]+")
_FORBIDDEN_HEADERS = (
    "rename from", "rename to", "copy from", "copy to", "new file mode",
    "deleted file mode", "old mode", "new mode", "similarity index",
    "dissimilarity index", "GIT binary patch", "Binary files",
)


@dataclass(frozen=True)
class Hunk:
    old_start: int
    old_len: int
    lines: tuple[tuple[str, str], ...]  # (tag, text); tag in " +-\\"


@dataclass(frozen=True)
class ParsedPatch:
    path: str
    hunks: tuple[Hunk, ...]

    @property
    def added(self) -> int:
        return sum(1 for h in self.hunks for t, _ in h.lines if t == "+")

    @property
    def removed(self) -> int:
        return sum(1 for h in self.hunks for t, _ in h.lines if t == "-")


@dataclass(frozen=True)
class PatchValidation:
    patched_content: str
    added_lines: int
    removed_lines: int
    hunk_count: int
    secret_findings: tuple[SecretFinding, ...]

    @property
    def safe(self) -> bool:
        return not self.secret_findings


def split_lines(text: str) -> list[str]:
    """Split on ``\\n`` only, keeping line endings (unlike ``str.splitlines``)."""
    return _LINE_RE.findall(text)


def _text(line: str) -> str:
    return line.removesuffix("\n").removesuffix("\r")


def is_binary_text(text: str) -> bool:
    return "\x00" in text


def _header_path(raw: str, expected: str) -> None:
    value = raw.split("\t")[0].strip()
    if value == "/dev/null":
        raise PatchSafetyError("Creating or deleting files is not permitted by this patch.")
    if value not in {expected, f"a/{expected}", f"b/{expected}"}:
        raise PatchSafetyError("Patch targets a file outside the approved scope.")


def parse_unified_diff(diff: str, *, expected_path: str) -> ParsedPatch:
    if not isinstance(diff, str) or not diff.strip():
        raise PatchSafetyError("Patch is empty.")
    if len(diff.encode("utf-8", "replace")) > MAX_PATCH_BYTES:
        raise PatchSafetyError("Patch is too large.")
    if "\x00" in diff:
        raise PatchSafetyError("Binary content in patch is not permitted.")
    lines = diff.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    i = 0
    seen_old = seen_new = seen_git = False
    while i < len(lines) and not lines[i].startswith("@@"):
        line = lines[i].rstrip("\r")
        if line.startswith(_FORBIDDEN_HEADERS):
            raise PatchSafetyError("Patch uses an unsupported feature (rename, mode, binary, create or delete).")
        if line.startswith("diff --git"):
            if seen_git:
                raise PatchSafetyError("Patch modifies more than one file.")
            seen_git = True
        elif line.startswith("--- "):
            if seen_old:
                raise PatchSafetyError("Patch modifies more than one file.")
            _header_path(line[4:], expected_path)
            seen_old = True
        elif line.startswith("+++ "):
            if seen_new:
                raise PatchSafetyError("Patch modifies more than one file.")
            _header_path(line[4:], expected_path)
            seen_new = True
        elif line.startswith("index ") or line == "":
            pass
        else:
            raise PatchSafetyError("Unexpected line in patch header.")
        i += 1
    if not (seen_old and seen_new):
        raise PatchSafetyError("Patch is missing file headers.")

    hunks: list[Hunk] = []
    while i < len(lines):
        match = _HUNK_RE.match(lines[i])
        if not match:
            raise PatchSafetyError(f"Unexpected content at patch line {i + 1}.")
        old_start = int(match.group(1))
        old_len = int(match.group(2)) if match.group(2) is not None else 1
        new_len = int(match.group(4)) if match.group(4) is not None else 1
        i += 1
        body: list[tuple[str, str]] = []
        old_seen = new_seen = 0
        while old_seen < old_len or new_seen < new_len:
            if i >= len(lines):
                raise PatchSafetyError("Patch hunk is truncated.")
            line = lines[i]
            tag, text = (" ", "") if line == "" else (line[0], line[1:])
            if tag == " " and old_seen < old_len and new_seen < new_len:
                old_seen += 1
                new_seen += 1
            elif tag == "-" and old_seen < old_len:
                old_seen += 1
            elif tag == "+" and new_seen < new_len:
                new_seen += 1
            else:
                raise PatchSafetyError("Patch hunk line counts are inconsistent.")
            body.append((tag, text))
            i += 1
            if i < len(lines) and lines[i].startswith("\\"):
                body.append(("\\", ""))
                i += 1
        if not any(t in "+-" for t, _ in body):
            raise PatchSafetyError("Patch hunk contains no changes.")
        hunks.append(Hunk(old_start=old_start, old_len=old_len, lines=tuple(body)))
    if not hunks:
        raise PatchSafetyError("Patch contains no hunks.")
    return ParsedPatch(path=expected_path, hunks=tuple(hunks))


def _dominant_eol(lines: list[str]) -> str:
    crlf = sum(1 for ln in lines if ln.endswith("\r\n"))
    lf = sum(1 for ln in lines if ln.endswith("\n") and not ln.endswith("\r\n"))
    return "\r\n" if crlf > lf else "\n"


def apply_patch(original: str, patch: ParsedPatch) -> str:
    src = split_lines(original)
    eol = _dominant_eol(src)
    out: list[str] = []
    pos = 0
    for hunk in patch.hunks:
        start = hunk.old_start if hunk.old_len == 0 else hunk.old_start - 1
        if start < pos or start > len(src):
            raise PatchApplyError("Patch hunks overlap or fall outside the file.")
        out.extend(src[pos:start])
        pos = start
        body = hunk.lines
        for idx, (tag, text) in enumerate(body):
            if tag == "\\":
                continue
            no_newline = idx + 1 < len(body) and body[idx + 1][0] == "\\"
            wanted = text.removesuffix("\r")
            if tag in " -":
                if pos >= len(src) or _text(src[pos]) != wanted:
                    raise PatchApplyError("Patch does not match the current file content.")
                if tag == " ":
                    out.append(src[pos])
                pos += 1
            else:
                out.append(wanted + ("" if no_newline else eol))
    out.extend(src[pos:])
    if any(not ln.endswith("\n") for ln in out[:-1]):
        raise PatchApplyError("Patch would corrupt line structure.")
    return "".join(out)


def validate_single_file_patch(
    diff: str,
    *,
    expected_path: str,
    original_content: str,
    max_bytes: int = DEFAULT_MAX_SOURCE_FILE_BYTES,
) -> PatchValidation:
    """Parse, apply and scan a patch. Raises ``PatchSafetyError`` on any violation."""
    validate_write_path(expected_path)
    validate_repo_path(expected_path)
    if is_binary_text(original_content):
        raise PatchSafetyError("Binary files cannot be patched.")
    parsed = parse_unified_diff(diff, expected_path=expected_path)
    patched = apply_patch(original_content, parsed)
    if patched == original_content:
        raise PatchSafetyError("Patch makes no effective change.")
    if len(patched.encode("utf-8")) > max_bytes:
        raise PatchSafetyError("Patched file exceeds the size limit.")
    findings = find_secrets_in_added_lines(original_content, patched)
    return PatchValidation(
        patched_content=patched,
        added_lines=parsed.added,
        removed_lines=parsed.removed,
        hunk_count=len(parsed.hunks),
        secret_findings=tuple(findings),
    )
