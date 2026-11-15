"""Repository tree rendering."""

from __future__ import annotations

from typing import Any, Sequence

import streamlit as st

from lib.formatting import fmt_bytes

_ICON = {"directory": "📁", "file": "📄", "symlink": "🔗", "submodule": "📦"}


def tree_lines(entries: Sequence[dict[str, Any]], *, max_lines: int = 600) -> list[str]:
    lines: list[str] = []
    for e in entries:
        depth = e["path"].count("/")
        name = e["path"].rsplit("/", 1)[-1]
        size = f"  ({fmt_bytes(e['size'])})" if e.get("size") is not None and e["kind"] == "file" else ""
        lines.append(f"{'    ' * depth}{_ICON.get(e['kind'], '•')} {name}{size}")
        if len(lines) >= max_lines:
            lines.append(f"… truncated at {max_lines} entries; use the filter to narrow the tree")
            break
    return lines


def render_tree(entries: Sequence[dict[str, Any]], *, key: str) -> list[dict[str, Any]]:
    """Filterable tree. Returns the entries currently shown."""
    c1, c2 = st.columns([3, 1])
    query = c1.text_input("Filter by path", key=f"{key}-q", placeholder="e.g. src/ or .py").strip().lower()
    kinds = c2.multiselect("Types", ["file", "directory", "symlink", "submodule"], default=["file", "directory"], key=f"{key}-k")
    shown = [e for e in entries if e["kind"] in kinds and (not query or query in e["path"].lower())]
    st.caption(f"{len(shown)} of {len(entries)} entries")
    st.code("\n".join(tree_lines(shown)) or "(nothing matches)", language="text")
    return shown
