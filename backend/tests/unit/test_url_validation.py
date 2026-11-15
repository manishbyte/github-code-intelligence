import unittest

from app.core.exceptions import InvalidInputError
from app.guardrails.input_validation import (
    parse_github_repo_url, validate_branch_name, validate_commit_sha, validate_owner_repo,
)


class RepoUrlTests(unittest.TestCase):
    def test_accepts_valid_forms(self):
        for url in ("https://github.com/octo/demo", "https://github.com/octo/demo/",
                    "https://github.com/octo/demo.git", "  https://GitHub.com/octo/demo  "):
            ref = parse_github_repo_url(url)
            self.assertEqual(ref.full_name, "octo/demo")

    def test_rejects_unsafe_urls(self):
        bad = [
            "http://github.com/octo/demo", "https://evil.com/octo/demo",
            "https://github.com.evil.com/octo/demo", "https://user:pw@github.com/octo/demo",
            "https://github.com:8443/octo/demo", "https://github.com/octo/demo?x=1",
            "https://github.com/octo/demo#frag", "https://github.com/octo/demo/tree/main",
            "https://github.com/octo", "octo/demo", "/etc/passwd", "file:///etc/passwd",
            "https://github.com/octo/%2e%2e", "https://github.com/octo/..", "",
            "https://github.com/octo/\ndemo", "https://github.com\\octo\\demo", "https://github.com/-bad/demo",
            "https://github.com/octo/" + "a" * 101, "git@github.com:octo/demo.git",
        ]
        for url in bad:
            with self.subTest(url=url):
                with self.assertRaises(InvalidInputError):
                    parse_github_repo_url(url)

    def test_owner_repo_and_sha_and_branch(self):
        self.assertEqual(validate_owner_repo("octo", "demo.js").name, "demo.js")
        with self.assertRaises(InvalidInputError):
            validate_owner_repo("octo", "../x")
        validate_commit_sha("a" * 40)
        for sha in ("main", "A" * 40, "a" * 39, "a" * 40 + "x"):
            with self.assertRaises(InvalidInputError):
                validate_commit_sha(sha)
        validate_branch_name("code-intel/fix-1")
        for name in ("", "-x", "a..b", "a//b", "a/.hidden", "x.lock", "a b", "a~b", "end.", "/lead", "a@{b"):
            with self.subTest(name=name), self.assertRaises(InvalidInputError):
                validate_branch_name(name)


if __name__ == "__main__":
    unittest.main()
