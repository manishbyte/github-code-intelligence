"""Deterministic patch construction for comment/logging proposals.

The model only proposes *insertions*. This module validates each one against
strict, language-aware rules, applies them itself, and produces the unified
diff with ``difflib``. The model never writes code or diffs that reach GitHub.
"""

from __future__ import annotations

import ast
import difflib
import io
import re
import tokenize
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from app.core.exceptions import InvalidInputError
from app.guardrails.patch_safety import split_lines
from app.guardrails.secret_detection import find_secrets
from app.schemas.code_change import RawEdit

LINE_COMMENT = {
    "python": "#", "ruby": "#", "shell": "#", "yaml": "#", "toml": "#", "dockerfile": "#", "makefile": "#",
    "javascript": "//", "typescript": "//", "java": "//", "go": "//", "rust": "//", "c": "//", "cpp": "//",
    "csharp": "//", "kotlin": "//", "swift": "//", "php": "//", "sql": "--",
}
C_LIKE = frozenset({"javascript", "typescript", "java", "go", "rust", "c", "cpp", "csharp", "kotlin", "swift", "php"})
_SENSITIVE_RE = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|credential|\bssn\b|private[_-]?key)")
MAX_LINE_LENGTH = 200


@dataclass(frozen=True)
class ValidEdit:
    after_line: int
    lines: tuple[str, ...]  # fully indented, without line endings


@dataclass(frozen=True)
class BuiltPatch:
    new_content: str
    diff: str
    applied_edits: int
    dropped: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------- helpers
def _indent(line: str) -> str:
    return re.match(r"[ \t]*", line).group(0)  # type: ignore[union-attr]


def detect_indent_unit(lines: Sequence[str]) -> str:
    smallest: int | None = None
    for ln in lines:
        if not ln.strip():
            continue
        if ln.startswith("\t"):
            return "\t"
        n = len(_indent(ln))
        if n:
            smallest = n if smallest is None else min(smallest, n)
    return " " * (smallest if smallest and smallest <= 8 else 4)


def _eol(lines: Sequence[str]) -> str:
    crlf = sum(1 for ln in lines if ln.endswith("\r\n"))
    lf = sum(1 for ln in lines if ln.endswith("\n") and not ln.endswith("\r\n"))
    return "\r\n" if crlf > lf else "\n"


def _text(line: str) -> str:
    return line.rstrip("\r\n")


def protected_after_lines(language: str, content: str) -> set[int]:
    """Insertion points (``after_line`` values) that would fall inside a multi-line string literal."""
    forbidden: set[int] = set()
    if language == "python":
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(content).readline))
        except (tokenize.TokenError, IndentationError, SyntaxError):
            raise InvalidInputError("This Python file cannot be analyzed safely for insertion points.") from None
        fstart: list[int] = []
        spans: list[tuple[int, int]] = []
        for t in tokens:
            name = tokenize.tok_name.get(t.type, "")
            if name == "FSTRING_START":
                fstart.append(t.start[0])
            elif name == "FSTRING_END" and fstart:
                spans.append((fstart.pop(), t.end[0]))
            elif t.type == tokenize.STRING:
                spans.append((t.start[0], t.end[0]))
        for start, end in spans:
            forbidden.update(range(start, end))
        return forbidden
    pattern = {
        "javascript": r"(?<!\\)`", "typescript": r"(?<!\\)`", "go": r"(?<!\\)`",
        "java": r'"""', "kotlin": r'"""', "swift": r'"""', "csharp": r'"""',
    }.get(language)
    if pattern:
        inside = False
        for i, line in enumerate(split_lines(content), start=1):
            if len(re.findall(pattern, line)) % 2 == 1:
                inside = not inside
            if inside:
                forbidden.add(i)
    return forbidden


# ---------------------------------------------------------------- comments
def detect_comment_conventions(language: str, content: str) -> dict[str, str]:
    token = LINE_COMMENT.get(language)
    if token is None:
        raise InvalidInputError(f"Comment generation is not supported for this language ({language}).")
    lines = content.split("\n")
    comment_lines = sum(1 for ln in lines if ln.strip().startswith(token))
    density = comment_lines / max(1, len(lines))
    note = "sparse comments" if density < 0.05 else "moderately commented" if density < 0.2 else "heavily commented"
    return {"line_comment": token, "style_note": note}


def validate_comment_edits(language: str, content: str, edits: Sequence[RawEdit], *, max_edits: int = 12) -> tuple[list[ValidEdit], list[str]]:
    token = LINE_COMMENT.get(language)
    if token is None:
        raise InvalidInputError(f"Comment generation is not supported for this language ({language}).")
    lines = split_lines(content)
    protected = protected_after_lines(language, content)
    valid: list[ValidEdit] = []
    dropped: list[str] = []
    seen: set[tuple[int, str]] = set()
    for e in edits:
        if len(valid) >= max_edits:
            dropped.append("edit limit reached")
            break
        if e.after_line > len(lines) or e.after_line in protected:
            dropped.append(f"invalid insertion point {e.after_line}")
            continue
        if e.after_line > 0 and _text(lines[e.after_line - 1]).rstrip().endswith("\\"):
            dropped.append(f"insertion after a continued line ({e.after_line})")
            continue
        texts = [t.strip() for t in e.text.split("\n") if t.strip()]
        ok = 0 < len(texts) <= 8 and all(
            len(t) <= MAX_LINE_LENGTH and not t.endswith("\\") and not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", t)
            and (t.startswith(token) or (language in C_LIKE and t.startswith(("/*", "*", "*/"))))
            for t in texts
        )
        if not ok or find_secrets("\n".join(texts)):
            dropped.append(f"non-comment or unsafe text at {e.after_line}")
            continue
        key = (e.after_line, "\n".join(texts))
        if key in seen:
            continue
        seen.add(key)
        ref = next((ln for ln in lines[e.after_line:] if ln.strip()), None) or (lines[e.after_line - 1] if e.after_line else "")
        valid.append(ValidEdit(e.after_line, tuple(_indent(ref) + t for t in texts)))
    return valid, dropped


# ---------------------------------------------------------------- logging
_PY_NAMES = re.compile(r"^(logger|log|_logger|_log)\s*=\s*", re.MULTILINE)


def detect_logging_convention(language: str, content: str) -> dict[str, object]:
    """Find the file's existing logging convention. Raises if none can be used safely."""
    if language == "python":
        found = _PY_NAMES.search(content)
        name = found.group(1) if found else "logger"
        return {"logger": name, "needs_setup": found is None, "example": f'{name}.info("message %s", value)'}
    if language in ("javascript", "typescript"):
        m = re.search(r"\b(logger|log)\.(?:info|debug|warn|error)\(", content)
        name = m.group(1) if m else "console"
        return {"logger": name, "needs_setup": False, "example": f'{name}.info("message", value);'}
    if language == "java":
        m = re.search(r"\bLogger\s+(\w+)\s*=", content)
        if m:
            return {"logger": m.group(1), "needs_setup": False, "example": f'{m.group(1)}.info("message {{}}", value);'}
    if language == "csharp":
        m = re.search(r"\bILogger(?:<[^>]+>)?\s+(\w+)", content)
        if m:
            return {"logger": m.group(1), "needs_setup": False, "example": f'{m.group(1)}.LogInformation("message {{Value}}", value);'}
    if language == "go":
        if '"log/slog"' in content:
            return {"logger": "slog", "needs_setup": False, "example": 'slog.Info("message", "key", value)'}
        if re.search(r'^\s*"log"\s*$|import\s+"log"', content, re.MULTILINE):
            return {"logger": "log", "needs_setup": False, "example": 'log.Printf("message %v", value)'}
    raise InvalidInputError("No usable logging convention was found in this file, so logging cannot be added safely.")


def _logging_regex(language: str, name: str) -> re.Pattern[str]:
    n = re.escape(name)
    patterns = {
        "python": rf"^{n}\.(debug|info|warning|error|exception|critical)\(.*\)\s*$",
        "javascript": rf"^{n}\.(debug|info|warn|error|log)\(.*\);?\s*$",
        "typescript": rf"^{n}\.(debug|info|warn|error|log)\(.*\);?\s*$",
        "java": rf"^{n}\.(trace|debug|info|warn|error)\(.*\);\s*$",
        "csharp": rf"^{n}\.Log(Trace|Debug|Information|Warning|Error)\(.*\);\s*$",
        "go": rf"^{n}\.(Printf|Println|Print|Info|Debug|Warn|Error)\(.*\)\s*$",
    }
    return re.compile(patterns[language])


def _python_setup_edit(content: str, convention: Mapping[str, object]) -> ValidEdit | None:
    if not convention.get("needs_setup"):
        return None
    try:
        tree = ast.parse(content)
    except SyntaxError:
        raise InvalidInputError("The Python file has a syntax error; logging cannot be added.") from None
    position = 0
    body = tree.body
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
        position = body[0].end_lineno or 0
    for node in body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            position = max(position, node.end_lineno or 0)
    lines: list[str] = []
    if not re.search(r"^\s*import logging\b", content, re.MULTILINE):
        lines.append("import logging")
    lines.append(f"{convention['logger']} = logging.getLogger(__name__)")
    return ValidEdit(position, tuple(lines))


def validate_logging_edits(
    language: str, content: str, edits: Sequence[RawEdit], convention: Mapping[str, object], *, max_edits: int = 10
) -> tuple[list[ValidEdit], list[str]]:
    if language not in ("python", "javascript", "typescript", "java", "csharp", "go"):
        raise InvalidInputError(f"Logging generation is not supported for this language ({language}).")
    lines = split_lines(content)
    protected = protected_after_lines(language, content)
    unit = detect_indent_unit([_text(l) for l in lines])
    regex = _logging_regex(language, str(convention["logger"]))
    valid: list[ValidEdit] = []
    dropped: list[str] = []
    seen: set[tuple[int, str]] = set()
    for e in edits:
        if len(valid) >= max_edits:
            dropped.append("edit limit reached")
            break
        stmt = e.text.strip()
        if "\n" in stmt or len(stmt) > MAX_LINE_LENGTH or not regex.match(stmt):
            dropped.append(f"not a single valid log statement at {e.after_line}")
            continue
        if _SENSITIVE_RE.search(stmt) or find_secrets(stmt):
            dropped.append(f"log statement mentions sensitive data at {e.after_line}")
            continue
        if not 1 <= e.after_line <= len(lines) or e.after_line in protected:
            dropped.append(f"invalid insertion point {e.after_line}")
            continue
        prev_raw = _text(lines[e.after_line - 1])
        prev = prev_raw.strip()
        nxt = next((ln.strip() for ln in lines[e.after_line:] if ln.strip()), "")
        if not prev or prev.endswith("\\") or prev.startswith(("return", "raise", "break", "continue", "throw", "@")):
            dropped.append(f"unsafe position after line {e.after_line}")
            continue
        if language == "python":
            if prev.endswith((",", "(", "[", "{")) or (prev.endswith(":") and nxt.startswith(('"""', "'''", '"', "'"))):
                dropped.append(f"unsafe position after line {e.after_line}")
                continue
            deeper = prev.endswith(":")
        elif language == "go":
            if prev.endswith(tuple(",(+-*/&|=.:")) and not prev.endswith("{"):
                dropped.append(f"unsafe position after line {e.after_line}")
                continue
            deeper = prev.endswith("{")
        else:
            if not prev.endswith(("{", ";", "}")):
                dropped.append(f"unsafe position after line {e.after_line}")
                continue
            deeper = prev.endswith("{")
        key = (e.after_line, stmt)
        if key in seen:
            continue
        seen.add(key)
        valid.append(ValidEdit(e.after_line, (_indent(prev_raw) + (unit if deeper else "") + stmt,)))
    if language == "python":
        setup = _python_setup_edit(content, convention)
        if setup is not None and valid:
            valid.append(setup)
    return valid, dropped


# ---------------------------------------------------------------- apply & diff
def apply_insertions(content: str, edits: Sequence[ValidEdit]) -> str:
    if not content.endswith("\n"):
        raise InvalidInputError("Files without a trailing newline are not supported for generated patches.")
    lines = split_lines(content)
    eol = _eol(lines)
    by_pos: dict[int, list[str]] = defaultdict(list)
    for e in sorted(edits, key=lambda x: x.after_line):
        by_pos[e.after_line].extend(e.lines)
    out: list[str] = []
    for idx in range(len(lines) + 1):
        out.extend(text + eol for text in by_pos.get(idx, ()))
        if idx < len(lines):
            out.append(lines[idx])
    return "".join(out)


def build_unified_diff(path: str, old: str, new: str) -> str:
    return "".join(difflib.unified_diff(split_lines(old), split_lines(new), fromfile=f"a/{path}", tofile=f"b/{path}", n=3))


class PatchAgent:
    """Facade used by the generation workflows."""

    @staticmethod
    def build(path: str, content: str, edits: Sequence[ValidEdit], dropped: Sequence[str] = ()) -> BuiltPatch:
        if not edits:
            raise InvalidInputError("No safe changes could be generated for this file.")
        new_content = apply_insertions(content, edits)
        return BuiltPatch(new_content, build_unified_diff(path, content, new_content), len(edits), tuple(dropped))
