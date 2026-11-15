"""In-memory GitHub REST double (test-only) implementing the HttpTransport protocol."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import unquote

from app.guardrails.action_policy import LedgerClaim
from app.integrations.github.client import RawResponse

OWNER, REPO = "octo", "demo"


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _h(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()


class FakeLedger:
    def __init__(self) -> None:
        self.entries: dict[str, dict[str, Any]] = {}

    async def claim(self, key: str) -> LedgerClaim:
        e = self.entries.get(key)
        if e is None:
            self.entries[key] = {"state": "in_progress"}
            return LedgerClaim("claimed")
        if e["state"] == "completed":
            return LedgerClaim("completed", e["result"])
        return LedgerClaim("in_progress")

    async def complete(self, key: str, result: Mapping[str, Any]) -> None:
        self.entries[key] = {"state": "completed", "result": dict(result)}

    async def fail(self, key: str, *, category: str, outcome_unknown: bool) -> None:
        self.entries[key] = {"state": "unknown" if outcome_unknown else "failed", "category": category}


class FakeGitHub:
    def __init__(self, files: dict[str, bytes] | None = None, *, push: bool = True,
                 private: bool = False, truncate_recursive: bool = False, login: str = "alice") -> None:
        self.login, self.push, self.private, self.truncate_recursive = login, push, private, truncate_recursive
        self.commits: dict[str, dict[str, bytes]] = {}
        self.branches: dict[str, str] = {}
        self.issues: list[dict[str, Any]] = []
        self.pulls: list[dict[str, Any]] = []
        self.calls: list[tuple[str, str]] = []
        self.trees: dict[str, tuple[str, str]] = {}
        self._n = 0
        if files is not None:
            self.branches["main"] = self._commit(dict(files))

    # -- state helpers
    def _commit(self, files: dict[str, bytes]) -> str:
        self._n += 1
        sha = _h(f"commit{self._n}")
        self.commits[sha] = files
        return sha

    def writes(self) -> list[tuple[str, str]]:
        return [c for c in self.calls if c[0] != "GET"]

    # -- transport
    async def send(self, method, url, *, headers, params, json_body, timeout):  # type: ignore[no-untyped-def]
        assert "Bearer " in headers["Authorization"]
        path = url.split("api.github.com", 1)[1]
        self.calls.append((method, path))
        status, body, extra = self._route(method, path, dict(params or {}), json_body)
        hdrs = {"x-github-request-id": "REQ1", **extra}
        return RawResponse(status, hdrs, json.dumps(body).encode())

    def _tree_entries(self, files: dict[str, bytes], prefix: str, recursive: bool, commit: str):
        out, seen = [], set()
        for p, data in sorted(files.items()):
            if not p.startswith(prefix):
                continue
            rel = p[len(prefix):]
            parts = rel.split("/")
            if len(parts) == 1:
                out.append({"path": rel, "type": "blob", "mode": "100644", "sha": blob_sha(data), "size": len(data)})
            else:
                dirs = [parts[0]] if not recursive else ["/".join(parts[: i + 1]) for i in range(len(parts) - 1)]
                for d in dirs:
                    if d not in seen:
                        seen.add(d)
                        tsha = _h(f"tree|{commit}|{prefix}{d}")
                        self.trees[tsha] = (commit, prefix + d + "/")
                        out.append({"path": d, "type": "tree", "mode": "040000", "sha": tsha})
                if recursive:
                    out.append({"path": rel, "type": "blob", "mode": "100644", "sha": blob_sha(data), "size": len(data)})
        return out

    def _route(self, method, path, params, body):  # noqa: C901
        R = rf"^/repos/{OWNER}/{REPO}"
        if method == "GET" and path == "/user":
            return 200, {"id": 7, "login": self.login, "html_url": f"https://github.com/{self.login}", "type": "User"}, {"x-oauth-scopes": "public_repo"}
        if method == "GET" and re.fullmatch(R, path):
            perms = {"admin": False, "push": self.push, "pull": True}
            return 200, {"name": REPO, "full_name": f"{OWNER}/{REPO}", "owner": {"login": OWNER},
                         "private": self.private, "visibility": "private" if self.private else "public",
                         "default_branch": "main", "html_url": f"https://github.com/{OWNER}/{REPO}",
                         "has_issues": True, "permissions": perms}, {}
        if m := re.fullmatch(R + r"/branches/(.+)", path):
            sha = self.branches.get(unquote(m[1]))
            return (200, {"commit": {"sha": sha}}, {}) if sha else (404, {"message": "Branch not found"}, {})
        if m := re.fullmatch(R + r"/git/ref/heads/(.+)", path):
            sha = self.branches.get(unquote(m[1]))
            return (200, {"object": {"sha": sha}}, {}) if sha else (404, {"message": "Not Found"}, {})
        if method == "POST" and re.fullmatch(R + "/git/refs", path):
            name = body["ref"].removeprefix("refs/heads/")
            if name in self.branches or body["sha"] not in self.commits:
                return 422, {"message": "Reference already exists"}, {}
            self.branches[name] = body["sha"]
            return 201, {"object": {"sha": body["sha"]}}, {}
        if m := re.fullmatch(R + r"/git/commits/([0-9a-f]+)", path):
            if m[1] not in self.commits:
                return 404, {"message": "Not Found"}, {}
            tsha = _h(f"tree|{m[1]}|")
            self.trees[tsha] = (m[1], "")
            return 200, {"sha": m[1], "tree": {"sha": tsha}}, {}
        if m := re.fullmatch(R + r"/git/trees/([0-9a-f]+)", path):
            commit, prefix = self.trees[m[1]]
            rec = params.get("recursive") == "1"
            entries = self._tree_entries(self.commits[commit], prefix, rec, commit)
            if rec and self.truncate_recursive:
                return 200, {"tree": entries[:1], "truncated": True}, {}
            return 200, {"tree": entries, "truncated": False}, {}
        if m := re.fullmatch(R + r"/contents/(.+)", path):
            p = unquote(m[1])
            if method == "GET":
                files = self.commits.get(params.get("ref", "")) or self.commits.get(self.branches.get(params.get("ref", ""), ""))
                if files is None:
                    return 404, {"message": "No commit found for the ref"}, {}
                if p in files:
                    d = files[p]
                    return 200, {"type": "file", "size": len(d), "sha": blob_sha(d), "encoding": "base64",
                                 "content": base64.encodebytes(d).decode()}, {}
                if any(f.startswith(p + "/") for f in files):
                    return 200, [{"name": "x"}], {}
                return 404, {"message": "Not Found"}, {}
            if method == "PUT":
                branch = body["branch"]
                files = self.commits[self.branches[branch]]
                if p not in files or blob_sha(files[p]) != body["sha"]:
                    return 409, {"message": "does not match"}, {}
                data = base64.b64decode(body["content"])
                new = self._commit({**files, p: data})
                self.branches[branch] = new
                return 200, {"content": {"sha": blob_sha(data)}, "commit": {"sha": new}}, {}
        if method == "GET" and re.fullmatch(R + "/commits", path):
            return 200, [{"sha": self.branches[params["sha"]]}], {}
        if re.fullmatch(R + "/issues", path):
            if method == "POST":
                n = len(self.issues) + 1
                self.issues.append({"number": n, "title": body["title"].strip(), "state": "open",
                                    "html_url": f"https://github.com/{OWNER}/{REPO}/issues/{n}"})
                return 201, self.issues[-1], {}
            return 200, self.issues, {}
        if m := re.fullmatch(R + r"/issues/(\d+)", path):
            return 200, self.issues[int(m[1]) - 1], {}
        if re.fullmatch(R + "/pulls", path):
            if method == "POST":
                n = len(self.pulls) + 1
                self.pulls.append({"number": n, "state": "open", "draft": body["draft"],
                                   "html_url": f"https://github.com/{OWNER}/{REPO}/pull/{n}",
                                   "head": {"ref": body["head"]}, "base": {"ref": body["base"]}})
                return 201, self.pulls[-1], {}
            head = params["head"].split(":", 1)[1]
            return 200, [p for p in self.pulls if p["head"]["ref"] == head and p["state"] == "open"], {}
        if m := re.fullmatch(R + r"/pulls/(\d+)", path):
            return 200, self.pulls[int(m[1]) - 1], {}
        return 404, {"message": "Not Found"}, {}
