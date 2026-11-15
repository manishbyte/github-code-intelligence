import unittest

from app.core.exceptions import InvalidInputError
from app.guardrails.path_safety import validate_repo_path, validate_write_path


class PathTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_repo_path("src/app/main.py"), "src/app/main.py")
        self.assertEqual(validate_repo_path("src/", allow_trailing_slash=True), "src")
        self.assertEqual(validate_repo_path("", allow_root=True), "")
        self.assertEqual(validate_repo_path("docs/100%25.md"), "docs/100%25.md")

    def test_traversal_and_malformed(self):
        bad = ["../x", "a/../b", "/abs", "a//b", "a/./b", "a\\b", "C:/x", "a/.git/config", ".GIT/x",
               "a\x00b", "a\nb", "%2e%2e/x", "a/%2e%2e/b", "a%2f..%2fb", "x/", "", "a/\u202eb",
               "a" * 1025]
        for p in bad:
            with self.subTest(p=p), self.assertRaises(InvalidInputError):
                validate_repo_path(p)

    def test_write_protection(self):
        for p in (".github/workflows/ci.yml", ".GitHub/Workflows/x.yml", ".github/actions/a/action.yml"):
            with self.subTest(p=p), self.assertRaises(InvalidInputError):
                validate_write_path(p)
        self.assertEqual(validate_write_path(".github/CODEOWNERS"), ".github/CODEOWNERS")


if __name__ == "__main__":
    unittest.main()
