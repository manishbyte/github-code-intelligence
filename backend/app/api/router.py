from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    analysis_history, approvals, auth, code_change_proposals, code_reviews, evaluations, files, github_accounts,
    github_actions, github_oauth, github_repositories, health, issue_proposals, repository_tree, users,
)

api_router = APIRouter(prefix="/api/v1")
for module in (
    health, auth, users, github_oauth, github_accounts, github_repositories, repository_tree, files, code_reviews,
    issue_proposals, code_change_proposals, approvals, github_actions, analysis_history, evaluations,
):
    api_router.include_router(module.router)
