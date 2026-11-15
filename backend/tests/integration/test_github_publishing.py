import importlib.util
import unittest

from app.guardrails.action_policy import WriteActionType
from app.integrations.github.client import GitHubClient
from tests.fixtures.approvals import NOW, make_approval
from tests.fixtures.fake_github import FakeGitHub, FakeLedger, OWNER, REPO, blob_sha

HAS_PYDANTIC = importlib.util.find_spec("pydantic") is not None
ORIG = b"a = 1\n"
NEW = "a = 2\n"
BRANCH = "code-intel/fix-a"


@unittest.skipUnless(HAS_PYDANTIC, "pydantic not installed")
class PublishingFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from app.tools import WriteToolContext
        self.fake = FakeGitHub({"m.py": ORIG})
        self.ledger = FakeLedger()
        self.ctx = WriteToolContext(user_id="u1", client=GitHubClient("tok", transport=self.fake, allow_writes=True),
                                    ledger=self.ledger, now=lambda: NOW)
        self.base = self.fake.branches["main"]

    async def test_full_publish_sequence_is_verified(self):
        from app.tools.github_write import create_branch as cb, create_commit as cc, create_issue as ci, create_pull_request as cp
        bp = cb.CreateBranchInput(owner=OWNER, repo=REPO, branch=BRANCH, from_sha=self.base)
        r1 = await cb.run(self.ctx, make_approval(WriteActionType.CREATE_BRANCH, cb.build_payload(bp), key="k-branch-01"), bp)
        self.assertEqual((r1.status, r1.verified, r1.github_sha, r1.replayed), ("succeeded", True, self.base, False))

        cip = cc.CreateCommitInput(owner=OWNER, repo=REPO, branch=BRANCH, path="m.py", content=NEW,
                                   message="fix: bump a", sha=blob_sha(ORIG))
        r2 = await cc.run(self.ctx, make_approval(WriteActionType.COMMIT_FILE, cc.build_payload(cip), key="k-commit-01"), cip)
        self.assertEqual(self.fake.commits[r2.github_sha]["m.py"], NEW.encode())
        self.assertEqual(self.fake.commits[self.base]["m.py"], ORIG)  # base untouched

        pp = cp.CreatePullRequestInput(owner=OWNER, repo=REPO, head=BRANCH, base="main", title="Fix a", body="b", draft=True)
        r3 = await cp.run(self.ctx, make_approval(WriteActionType.CREATE_PULL_REQUEST, cp.build_payload(pp), key="k-pr-0001"), pp)
        self.assertEqual(r3.github_number, 1)
        self.assertTrue(self.fake.pulls[0]["draft"])

        ip = ci.CreateIssueInput(owner=OWNER, repo=REPO, title="  Found bug ", body="details", labels=["bug"])
        r4 = await ci.run(self.ctx, make_approval(WriteActionType.CREATE_ISSUE, ci.build_payload(ip), key="k-issue-01"), ip)
        self.assertEqual((r4.github_number, r4.github_url), (1, f"https://github.com/{OWNER}/{REPO}/issues/1"))

    async def test_replay_with_same_approval_does_not_write_twice(self):
        from app.tools.github_write import create_issue as ci
        ip = ci.CreateIssueInput(owner=OWNER, repo=REPO, title="Bug", body="x")
        appr = make_approval(WriteActionType.CREATE_ISSUE, ci.build_payload(ip))
        first = await ci.run(self.ctx, appr, ip)
        second = await ci.run(self.ctx, appr, ip)
        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        self.assertEqual(len(self.fake.issues), 1)

    async def test_in_progress_claim_blocks_concurrent_duplicate(self):
        from app.core.exceptions import ActionInProgressError
        from app.tools.github_write import create_issue as ci
        ip = ci.CreateIssueInput(owner=OWNER, repo=REPO, title="Bug")
        appr = make_approval(WriteActionType.CREATE_ISSUE, ci.build_payload(ip))
        await self.ledger.claim(appr.idempotency_key)
        with self.assertRaises(ActionInProgressError):
            await ci.run(self.ctx, appr, ip)
        self.assertEqual(self.fake.writes(), [])

    async def test_pull_request_is_not_duplicated(self):
        from app.tools.github_write import create_branch as cb, create_pull_request as cp
        self.fake.branches[BRANCH] = self.base
        pp = cp.CreatePullRequestInput(owner=OWNER, repo=REPO, head=BRANCH, base="main", title="t")
        await cp.run(self.ctx, make_approval(WriteActionType.CREATE_PULL_REQUEST, cp.build_payload(pp), key="k-pr-0001"), pp)
        again = await cp.run(self.ctx, make_approval(WriteActionType.CREATE_PULL_REQUEST, cp.build_payload(pp), key="k-pr-0002"), pp)
        self.assertEqual((len(self.fake.pulls), again.github_number), (1, 1))

    async def test_interrupted_commit_is_reconciled_not_rewritten(self):
        from app.tools.github_write import create_commit as cc
        self.fake.branches[BRANCH] = self.fake._commit({"m.py": NEW.encode()})  # already applied
        cip = cc.CreateCommitInput(owner=OWNER, repo=REPO, branch=BRANCH, path="m.py", content=NEW, message="m", sha=blob_sha(ORIG))
        r = await cc.run(self.ctx, make_approval(WriteActionType.COMMIT_FILE, cc.build_payload(cip)), cip)
        self.assertEqual(r.github_sha, self.fake.branches[BRANCH])
        self.assertNotIn(("PUT", f"/repos/{OWNER}/{REPO}/contents/m.py"), self.fake.calls)

    async def test_unverifiable_write_is_not_reported_as_success(self):
        from app.core.exceptions import UnverifiedResultError
        from app.tools.github_write import create_issue as ci
        ip = ci.CreateIssueInput(owner=OWNER, repo=REPO, title="Bug")
        orig_route = self.fake._route

        def tamper(method, path, params, body):
            status, data, extra = orig_route(method, path, params, body)
            if method == "GET" and path.endswith("/issues/1"):
                data = {**data, "title": "Different"}
            return status, data, extra

        self.fake._route = tamper
        appr = make_approval(WriteActionType.CREATE_ISSUE, ci.build_payload(ip))
        with self.assertRaises(UnverifiedResultError):
            await ci.run(self.ctx, appr, ip)
        self.assertEqual(self.ledger.entries[appr.idempotency_key]["state"], "unknown")


if __name__ == "__main__":
    unittest.main()
