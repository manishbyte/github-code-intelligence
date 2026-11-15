"""Shared constants. Contains no secrets and no deployment-specific values."""

from __future__ import annotations

GITHUB_WEB_HOST = "github.com"
GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
HTTP_USER_AGENT = "github-code-intelligence"

DEFAULT_MAX_SOURCE_FILE_BYTES = 500_000
MAX_PATH_LENGTH = 1024
MAX_PATCH_BYTES = 1_000_000
MAX_TREE_ENTRIES = 200_000

MAX_ISSUE_TITLE_LENGTH = 256
MAX_ISSUE_BODY_LENGTH = 60_000
MAX_COMMIT_MESSAGE_LENGTH = 1_000
MAX_PULL_REQUEST_BODY_LENGTH = 60_000

# Every branch created by this application must live under this prefix, so the
# application can never create or target the default branch or a user branch.
APPLICATION_BRANCH_PREFIX = "code-intel/"

# Paths the application never writes, even with approval (CI/automation surface).
PROTECTED_WRITE_PATH_PREFIXES = (".git/", ".github/workflows/", ".github/actions/")
