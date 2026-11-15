import dataclasses
import importlib.util
import unittest
from datetime import timedelta

from app.guardrails.action_policy import WriteActionType
from app.integrations.github.client import GitHubClient
from tests.fixtures.approvals import NOW, make_approval
from tests.fixtures.fake_github import FakeGitHub, FakeLedger, OWNER, REPO

HAS_PYDANTIC = importlib.util.find_spec("pydantic") is not None


@unittest.skipUnless(HAS_PYDANTIC, "pydantic not installed")
class HitlBypassTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from app.tools import WriteToolContext
        from app.tools.github_write import create_issue as ci
        self.ci = ci
        self.fake = FakeGitHub({"m.py": b"x\n"})
        self.ctx = WriteToolContext(user_id="u1", client=GitHubClient("tok", transport=self.fake, allow_writes=True),
                                    ledger=FakeLedger(), now=lambda: NOW)
        self.params = ci.CreateIssueInput(owner=OWNER, repo=REPO, title="Bug", body="b")
        self.payload = ci.build_payload(self.params)

    async def assert_blocked(self, approval):
        from app.core.exceptions import ApprovalError
        with self.assertRaises(ApprovalError):
            await self.ci.run(self.ctx, approval, self.params)
        self.assertEqual(self.fake.writes(), [])
        self.assertEqual(self.fake.issues, [])

    async def test_missing_or_forged_approval(self):
        await self.assert_blocked(None)
        await self.assert_blocked({"status": "PUBLISHING"})

    async def test_wrong_status(self):
        for status in ("PENDING_REVIEW", "APPROVED", "REJECTED", "PUBLISHED", "FAILED"):
            await self.assert_blocked(make_approval(WriteActionType.CREATE_ISSUE, self.payload, status=status))

    async def test_wrong_user_or_approver(self):
        await self.assert_blocked(make_approval(WriteActionType.CREATE_ISSUE, self.payload, user="u2"))
        await self.assert_blocked(make_approval(WriteActionType.CREATE_ISSUE, self.payload, approved_by="u2"))

    async def test_expired(self):
        await self.assert_blocked(make_approval(WriteActionType.CREATE_ISSUE, self.payload, expires=NOW - timedelta(seconds=1)))

    async def test_tampered_payload_after_approval(self):
        approval = make_approval(WriteActionType.CREATE_ISSUE, self.payload)
        self.params = self.ci.CreateIssueInput(owner=OWNER, repo=REPO, title="Bug", body="b + injected text")
        await self.assert_blocked(approval)

    async def test_wrong_action_type_or_repo(self):
        await self.assert_blocked(make_approval(WriteActionType.CREATE_BRANCH, self.payload))
        await self.assert_blocked(make_approval(WriteActionType.CREATE_ISSUE, self.payload, repo="other"))

    async def test_approval_is_immutable(self):
        approval = make_approval(WriteActionType.CREATE_ISSUE, self.payload, status="APPROVED")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            approval.status = "PUBLISHING"  # type: ignore[misc]
