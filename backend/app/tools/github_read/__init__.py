"""Read-only GitHub tools. Safe to expose to workflows/agents."""

from app.tools.github_read import (
    check_permissions,
    get_file_content,
    get_repository,
    get_repository_tree,
    get_user_profile,
)

READ_TOOLS = {
    m.TOOL_NAME: m
    for m in (check_permissions, get_file_content, get_repository, get_repository_tree, get_user_profile)
}
