import importlib.util
import unittest

from app.integrations.github.client import GitHubClient
from tests.fixtures.fake_github import FakeGitHub, OWNER, REPO

HAS_PYDANTIC = importlib.util.find_spec("pydantic") is not None
FILES = {"README.md": b"hi", "src/a.py": b"x = 1\n", "src/pkg/b.py": b"22", "bin.dat": b"\xff\x00\x01",
         "creds.py": b"t = 'ghp_" + b"Q" * 36 + b"'\n"}


@unittest.skipUnless(HAS_PYDANTIC, "pydantic not installed")
class ReadToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from app.tools import ToolContext
        self.fake = FakeGitHub(FILES)
        self.ctx = ToolContext(user_id="u1", client=GitHubClient("tok", transport=self.fake))
        self.sha = self.fake.branches["main"]

    async def test_get_repository(self):
        from app.tools.github_read.get_repository import GetRepositoryInput, run
        info = await run(self.ctx, GetRepositoryInput(repository_url=f"https://github.com/{OWNER}/{REPO}"))
        self.assertEqual((info.default_branch, info.default_branch_head_sha, info.is_empty), ("main", self.sha, False))

    async def test_private_repo_rejected_and_bad_url_rejected(self):
        from app.core.exceptions import InvalidInputError
        from app.tools import ToolContext
        from app.tools.github_read.get_repository import GetRepositoryInput, run
        ctx = ToolContext(user_id="u1", client=GitHubClient("tok", transport=FakeGitHub(FILES, private=True)))
        with self.assertRaises(InvalidInputError):
            await run(ctx, GetRepositoryInput(repository_url=f"https://github.com/{OWNER}/{REPO}"))
        with self.assertRaises(InvalidInputError):
            await run(self.ctx, GetRepositoryInput(repository_url="https://evil.com/a/b"))

    async def test_empty_repository(self):
        from app.tools import ToolContext
        from app.tools.github_read.get_repository import GetRepositoryInput, run
        ctx = ToolContext(user_id="u1", client=GitHubClient("tok", transport=FakeGitHub(None)))
        info = await run(ctx, GetRepositoryInput(repository_url=f"https://github.com/{OWNER}/{REPO}"))
        self.assertTrue(info.is_empty)
        self.assertIsNone(info.default_branch_head_sha)

    async def test_tree_with_filter(self):
        from app.tools.github_read.get_repository_tree import GetRepositoryTreeInput, run
        tree = await run(self.ctx, GetRepositoryTreeInput(owner=OWNER, repo=REPO, commit_sha=self.sha, path_filter="src"))
        self.assertEqual([e.path for e in tree.entries], ["src", "src/a.py", "src/pkg", "src/pkg/b.py"])
        self.assertEqual((tree.file_count, tree.directory_count), (2, 2))

    async def test_file_content_variants(self):
        from app.tools.github_read.get_file_content import GetFileContentInput, run

        async def get(path):
            return await run(self.ctx, GetFileContentInput(owner=OWNER, repo=REPO, path=path, commit_sha=self.sha))

        ok = await get("src/a.py")
        self.assertEqual((ok.status, ok.content, ok.language, ok.line_count, ok.content_trust), ("ok", "x = 1\n", "python", 1, "untrusted"))
        self.assertEqual((await get("bin.dat")).status, "binary")
        self.assertEqual((await get("nope.txt")).status, "not_found")
        self.assertEqual((await get("src")).status, "not_a_file")
        secret = await get("creds.py")
        self.assertEqual(secret.secret_findings[0].rule, "github_token")
        self.assertNotIn("Q" * 36, secret.secret_findings[0].preview)

    async def test_file_too_large_and_traversal(self):
        from app.core.exceptions import InvalidInputError
        from app.tools import ToolContext
        from app.tools.github_read.get_file_content import GetFileContentInput, run
        ctx = ToolContext(user_id="u1", client=self.ctx.client, max_file_bytes=3)
        r = await run(ctx, GetFileContentInput(owner=OWNER, repo=REPO, path="src/a.py", commit_sha=self.sha))
        self.assertEqual((r.status, r.content), ("too_large", None))
        with self.assertRaises(InvalidInputError):
            await run(self.ctx, GetFileContentInput(owner=OWNER, repo=REPO, path="../etc/passwd", commit_sha=self.sha))

    async def test_permissions_and_profile(self):
        from app.tools.github_read.check_permissions import CheckPermissionsInput, run
        from app.tools.github_read.get_user_profile import GetUserProfileInput, run as profile
        p = await run(self.ctx, CheckPermissionsInput(owner=OWNER, repo=REPO))
        self.assertEqual((p.github_login, p.can_push, p.can_create_issue, p.permissions_reported), ("alice", True, True, True))
        prof = await profile(self.ctx, GetUserProfileInput())
        self.assertEqual((prof.login, prof.granted_scopes), ("alice", ["public_repo"]))

    def test_read_context_rejects_write_client(self):
        from app.tools import ToolContext
        with self.assertRaises(ValueError):
            ToolContext(user_id="u1", client=GitHubClient("tok", transport=self.fake, allow_writes=True))


if __name__ == "__main__":
    unittest.main()
