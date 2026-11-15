import importlib.util
import unittest

from app.core.exceptions import (
    InvalidInputError, PermissionDeniedError, StaleSourceError,
)
from app.guardrails.action_policy import WriteActionType
from app.integrations.github.client import GitHubClient
from app.integrations.github.exceptions import ForbiddenOperationError, GitHubConflictError
from tests.fixtures.approvals import NOW, make_approval
from tests.fixtures.fake_github import FakeGitHub, FakeLedger, OWNER, REPO, blob_sha

HAS_PYDANTIC = importlib.util.find_spec("pydantic") is not None
ORIG = b"a = 1\n"


class ReadOnlyClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_client_cannot_write_at_all(self):
        fake = FakeGitHub({"m.py": ORIG})
        c = GitHubClient("tok", transport=fake)
        for method, path in [("POST", f"/repos/{OWNER}/{REPO}/issues"), ("PUT", f"/repos/{OWNER}/{REPO}/contents/m.py"),
                             ("POST", f"/repos/{OWNER}/{REPO}/git/refs"), ("POST", f"/repos/{OWNER}/{REPO}/pulls")]:
            with self.assertRaises(ForbiddenOperationError):
                await c.request(method, path, json_body={})
        self.assertEqual(fake.calls, [])


@unittest.skipUnless(HAS_PYDANTIC, "pydantic not installed")
class WriteToolGuardTests(unittest.IsolatedAsyncioTestCase):
    def make_ctx(self, **kw):
        from app.tools import WriteToolContext
        self.fake = FakeGitHub({"m.py": ORIG}, **kw)
        self.base = self.fake.branches["main"]
        return WriteToolContext(user_id="u1", client=GitHubClient("tok", transport=self.fake, allow_writes=True),
                                ledger=FakeLedger(), now=lambda: NOW)

    def commit_args(self, **over):
        from app.tools.github_write import create_commit as cc
        args = dict(owner=OWNER, repo=REPO, branch="code-intel/x", path="m.py", content="a = 2\n", message="m", sha=blob_sha(ORIG))
        args.update(over)
        p = cc.CreateCommitInput(**args)
        return cc, p, make_approval(WriteActionType.COMMIT_FILE, cc.build_payload(p))

    async def test_contexts_enforce_client_mode(self):
        from app.tools import WriteToolContext
        with self.assertRaises(ValueError):
            WriteToolContext(user_id="u1", client=GitHubClient("tok", transport=FakeGitHub({})), ledger=FakeLedger())

    async def test_no_push_permission_blocks_every_write(self):
        from app.tools.github_write import create_branch as cb, create_issue as ci
        ctx = self.make_ctx(push=False)
        self.fake.branches["code-intel/x"] = self.base
        cc, p, a = self.commit_args()
        with self.assertRaises(PermissionDeniedError):
            await cc.run(ctx, a, p)
        bp = cb.CreateBranchInput(owner=OWNER, repo=REPO, branch="code-intel/y", from_sha=self.base)
        with self.assertRaises(PermissionDeniedError):
            await cb.run(ctx, make_approval(WriteActionType.CREATE_BRANCH, cb.build_payload(bp)), bp)
        self.assertEqual(self.fake.writes(), [])
        # issues need no push access on a public repo with issues enabled
        ip = ci.CreateIssueInput(owner=OWNER, repo=REPO, title="t")
        self.assertEqual((await ci.run(ctx, make_approval(WriteActionType.CREATE_ISSUE, ci.build_payload(ip)), ip)).github_number, 1)

    async def test_branch_and_path_restrictions(self):
        ctx = self.make_ctx()
        for over in ({"branch": "main"}, {"branch": "feature/x"}, {"branch": "code-intel/../main"},
                     {"path": ".github/workflows/ci.yml"}, {"path": "../x.py"}, {"content": "a\x00b"}):
            cc, p, a = self.commit_args(**over)
            with self.subTest(over=over), self.assertRaises(InvalidInputError):
                await cc.run(ctx, a, p)
        self.assertEqual(self.fake.writes(), [])

    async def test_branch_creation_restrictions(self):
        from app.tools.github_write import create_branch as cb
        ctx = self.make_ctx()
        for name in ("main", "release", "code-intel/"):
            bp = cb.CreateBranchInput(owner=OWNER, repo=REPO, branch=name, from_sha=self.base)
            with self.subTest(name=name), self.assertRaises(InvalidInputError):
                await cb.run(ctx, make_approval(WriteActionType.CREATE_BRANCH, cb.build_payload(bp)), bp)
        self.assertEqual(self.fake.writes(), [])

    async def test_stale_source_is_refused(self):
        ctx = self.make_ctx()
        self.fake.branches["code-intel/x"] = self.fake._commit({"m.py": b"a = 999\n"})  # someone changed it
        cc, p, a = self.commit_args()
        with self.assertRaises(StaleSourceError):
            await cc.run(ctx, a, p)
        self.assertEqual(self.fake.writes(), [])

    async def test_commit_adding_a_secret_is_refused(self):
        ctx = self.make_ctx()
        self.fake.branches["code-intel/x"] = self.base
        cc, p, a = self.commit_args(content="a = 'ghp_" + "B" * 36 + "'\n")
        with self.assertRaises(InvalidInputError):
            await cc.run(ctx, a, p)
        self.assertEqual(self.fake.writes(), [])

    async def test_secret_in_issue_and_pr_text_refused(self):
        from app.tools.github_write import create_issue as ci
        ctx = self.make_ctx()
        ip = ci.CreateIssueInput(owner=OWNER, repo=REPO, title="t", body="key AKIAABCDEFGHIJKLMNOP")
        with self.assertRaises(InvalidInputError):
            await ci.run(ctx, make_approval(WriteActionType.CREATE_ISSUE, ci.build_payload(ip)), ip)
        self.assertEqual(self.fake.issues, [])

    async def test_existing_branch_at_other_commit_conflicts(self):
        from app.tools.github_write import create_branch as cb
        ctx = self.make_ctx()
        self.fake.branches["code-intel/x"] = self.fake._commit({"m.py": b"other\n"})
        bp = cb.CreateBranchInput(owner=OWNER, repo=REPO, branch="code-intel/x", from_sha=self.base)
        with self.assertRaises(GitHubConflictError):
            await cb.run(ctx, make_approval(WriteActionType.CREATE_BRANCH, cb.build_payload(bp)), bp)
        self.assertEqual(self.fake.writes(), [])

    async def test_extra_fields_rejected(self):
        from pydantic import ValidationError
        from app.tools.github_write import create_issue as ci
        with self.assertRaises(ValidationError):
            ci.CreateIssueInput(owner=OWNER, repo=REPO, title="t", assignees=["bob"])


if __name__ == "__main__":
    unittest.main()
