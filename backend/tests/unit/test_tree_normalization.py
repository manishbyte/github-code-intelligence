import unittest

from app.integrations.github.client import GitHubClient
from app.integrations.github.trees import fetch_complete_tree, normalize_tree_entries
from tests.fixtures.fake_github import FakeGitHub, OWNER, REPO

FILES = {"README.md": b"hi", "src/a.py": b"1", "src/pkg/b.py": b"22", "docs/x.md": b"3"}


class NormalizeTests(unittest.TestCase):
    def test_kinds_sorting_and_unsafe_skipped(self):
        raw = [
            {"path": "z.txt", "type": "blob", "mode": "100644", "sha": "s1", "size": 1},
            {"path": "link", "type": "blob", "mode": "120000", "sha": "s2"},
            {"path": "sub", "type": "commit", "mode": "160000", "sha": "s3"},
            {"path": "src", "type": "tree", "mode": "040000", "sha": "s4"},
            {"path": "src/a.py", "type": "blob", "mode": "100644", "sha": "s5", "size": 2},
            {"path": "../evil", "type": "blob", "mode": "100644", "sha": "s6"},
            {"path": "x", "type": "weird", "sha": "s7"},
            {"path": "z.txt", "type": "blob", "mode": "100644", "sha": "s1", "size": 1},
        ]
        entries, skipped = normalize_tree_entries(raw)
        self.assertEqual(skipped, 2)
        self.assertEqual([e.path for e in entries], ["link", "src", "src/a.py", "sub", "z.txt"])
        kinds = {e.path: e.kind for e in entries}
        self.assertEqual((kinds["link"], kinds["sub"], kinds["src"]), ("symlink", "submodule", "directory"))


class FetchTreeTests(unittest.IsolatedAsyncioTestCase):
    async def fetch(self, **kw):
        fake = FakeGitHub(FILES, **kw)
        client = GitHubClient("tok", transport=fake)
        return fake, await fetch_complete_tree(client, OWNER, REPO, fake.branches["main"])

    async def test_complete_tree(self):
        _, tree = await self.fetch()
        paths = [e.path for e in tree.entries]
        self.assertEqual({p for p in paths if "." in p}, {"README.md", "docs/x.md", "src/a.py", "src/pkg/b.py"})
        self.assertEqual(sum(e.kind == "directory" for e in tree.entries), 3)

    async def test_truncated_response_is_walked_level_by_level(self):
        _, full = await self.fetch()
        _, walked = await self.fetch(truncate_recursive=True)
        self.assertEqual([e.path for e in walked.entries], [e.path for e in full.entries])


if __name__ == "__main__":
    unittest.main()
