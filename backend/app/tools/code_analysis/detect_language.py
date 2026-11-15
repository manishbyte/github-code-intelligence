"""Language detection from filename, extension or shebang. Pure and deterministic."""

from __future__ import annotations

import os

from pydantic import Field

from app.schemas.code_change import LanguageResult
from app.schemas.common import StrictModel

TOOL_NAME = "detect_language"

_EXT = {
    ".py": "python", ".pyi": "python", ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript", ".java": "java", ".go": "go",
    ".rs": "rust", ".rb": "ruby", ".php": "php", ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp",
    ".hpp": "cpp", ".cs": "csharp", ".kt": "kotlin", ".swift": "swift", ".sh": "shell", ".bash": "shell",
    ".sql": "sql", ".html": "html", ".css": "css", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".md": "markdown", ".xml": "xml",
}
_NAMES = {"dockerfile": "dockerfile", "makefile": "makefile"}
_SHEBANG = (("python", "python"), ("node", "javascript"), ("ruby", "ruby"), ("bash", "shell"), ("sh", "shell"))


class DetectLanguageInput(StrictModel):
    path: str = Field(min_length=1, max_length=1024)
    first_line: str | None = Field(default=None, max_length=300)


def guess_language(path: str, first_line: str | None = None) -> LanguageResult:
    base = os.path.basename(path).lower()
    if base in _NAMES:
        return LanguageResult(language=_NAMES[base], method="filename")
    ext = os.path.splitext(base)[1]
    if ext in _EXT:
        return LanguageResult(language=_EXT[ext], method="extension")
    if first_line and first_line.startswith("#!"):
        interpreter = os.path.basename(first_line[2:].split()[-1] if "env" in first_line else first_line[2:].split()[0])
        for needle, language in _SHEBANG:
            if interpreter.startswith(needle):
                return LanguageResult(language=language, method="shebang")
    return LanguageResult(language=None, method="unknown")


def run(params: DetectLanguageInput) -> LanguageResult:
    return guess_language(params.path, params.first_line)
