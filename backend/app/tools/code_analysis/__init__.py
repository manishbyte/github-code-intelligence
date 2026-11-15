"""Pure code-analysis tools (synchronous, no network, never execute repository code)."""

from app.tools.code_analysis import (
    detect_language,
    inspect_secrets,
    run_quality_checks,
    validate_line_ranges,
    validate_patch,
)

CODE_ANALYSIS_TOOLS = {
    m.TOOL_NAME: m
    for m in (detect_language, inspect_secrets, run_quality_checks, validate_line_ranges, validate_patch)
}
