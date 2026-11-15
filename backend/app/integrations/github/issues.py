"""Issue operations. ``create_issue`` is a write and requires a write-enabled client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.integrations.github.client import GitHubClient, as_mapping
from app.integrations.github.exceptions import GitHubError


@dataclass(frozen=True)
class IssueData:
    number: int
    title: str
    state: str
    html_url: str
    request_id: str | None = None


def _issue(data: object, request_id: str | None) -> IssueData:
    d = as_mapping(data, "issue")
    if not (isinstance(d.get("number"), int) and isinstance(d.get("title"), str) and isinstance(d.get("html_url"), str)):
        raise GitHubError("Unexpected GitHub issue response.")
    return IssueData(d["number"], d["title"], str(d.get("state", "")), d["html_url"], request_id)


async def get_issue(client: GitHubClient, owner: str, repo: str, number: int) -> IssueData:
    resp = await client.request("GET", f"/repos/{owner}/{repo}/issues/{number}")
    return _issue(resp.data, resp.request_id)


async def list_open_issues(client: GitHubClient, owner: str, repo: str, *, limit: int = 100) -> list[IssueData]:
    resp = await client.request(
        "GET", f"/repos/{owner}/{repo}/issues", params={"state": "open", "per_page": str(min(limit, 100))}
    )
    if not isinstance(resp.data, list):
        raise GitHubError("Unexpected GitHub issues response.")
    return [_issue(i, resp.request_id) for i in resp.data if isinstance(i, dict) and "pull_request" not in i]


async def create_issue(
    client: GitHubClient, owner: str, repo: str, *, title: str, body: str, labels: Sequence[str] = ()
) -> IssueData:
    payload: dict[str, object] = {"title": title, "body": body}
    if labels:
        payload["labels"] = list(labels)
    resp = await client.request("POST", f"/repos/{owner}/{repo}/issues", json_body=payload)
    return _issue(resp.data, resp.request_id)
