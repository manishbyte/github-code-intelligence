"""Pull request operations. ``create_pull_request`` is a write."""

from __future__ import annotations

from dataclasses import dataclass

from app.integrations.github.client import GitHubClient, as_mapping
from app.integrations.github.exceptions import GitHubError


@dataclass(frozen=True)
class PullRequestData:
    number: int
    html_url: str
    state: str
    head_ref: str
    base_ref: str
    draft: bool
    request_id: str | None = None


def _pr(data: object, request_id: str | None) -> PullRequestData:
    d = as_mapping(data, "pull request")
    head, base = d.get("head"), d.get("base")
    if not (
        isinstance(d.get("number"), int) and isinstance(d.get("html_url"), str)
        and isinstance(head, dict) and isinstance(head.get("ref"), str)
        and isinstance(base, dict) and isinstance(base.get("ref"), str)
    ):
        raise GitHubError("Unexpected GitHub pull request response.")
    return PullRequestData(
        d["number"], d["html_url"], str(d.get("state", "")), head["ref"], base["ref"], bool(d.get("draft")), request_id
    )


async def get_pull_request(client: GitHubClient, owner: str, repo: str, number: int) -> PullRequestData:
    resp = await client.request("GET", f"/repos/{owner}/{repo}/pulls/{number}")
    return _pr(resp.data, resp.request_id)


async def find_open_pull_request(
    client: GitHubClient, owner: str, repo: str, head: str, base: str
) -> PullRequestData | None:
    resp = await client.request(
        "GET", f"/repos/{owner}/{repo}/pulls",
        params={"state": "open", "head": f"{owner}:{head}", "base": base, "per_page": "1"},
    )
    if not isinstance(resp.data, list):
        raise GitHubError("Unexpected GitHub pull request list response.")
    return _pr(resp.data[0], resp.request_id) if resp.data else None


async def create_pull_request(
    client: GitHubClient, owner: str, repo: str, *, title: str, head: str, base: str, body: str, draft: bool
) -> PullRequestData:
    resp = await client.request(
        "POST", f"/repos/{owner}/{repo}/pulls",
        json_body={"title": title, "head": head, "base": base, "body": body, "draft": draft},
    )
    return _pr(resp.data, resp.request_id)
