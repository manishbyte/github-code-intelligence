import unittest

from app.core.exceptions import GuardrailViolation, PatchApplyError, PatchSafetyError
from app.guardrails.patch_safety import validate_single_file_patch

ORIG = "a = 1\nb = 2\nc = 3\n"


def diff(body: str, path: str = "m.py") -> str:
    return f"--- a/{path}\n+++ b/{path}\n{body}"


class PatchTests(unittest.TestCase):
    def check(self, d, orig=ORIG, path="m.py"):
        return validate_single_file_patch(d, expected_path=path, original_content=orig)

    def test_applies(self):
        r = self.check(diff("@@ -1,3 +1,3 @@\n a = 1\n-b = 2\n+b = 20\n c = 3\n"))
        self.assertEqual(r.patched_content, "a = 1\nb = 20\nc = 3\n")
        self.assertEqual((r.added_lines, r.removed_lines, r.hunk_count), (1, 1, 1))
        self.assertTrue(r.safe)

    def test_git_headers_and_insert_at_end(self):
        d = "diff --git a/m.py b/m.py\nindex 1..2 100644\n" + diff("@@ -3,1 +3,2 @@\n c = 3\n+d = 4\n")
        self.assertEqual(self.check(d).patched_content, ORIG + "d = 4\n")

    def test_crlf_preserved(self):
        orig = "a\r\nb\r\n"
        r = self.check(diff("@@ -1,2 +1,3 @@\n a\n+x\n b\n"), orig)
        self.assertEqual(r.patched_content, "a\r\nx\r\nb\r\n")

    def test_no_newline_at_eof(self):
        orig = "a\nb"
        d = diff("@@ -1,2 +1,2 @@\n a\n-b\n\\ No newline at end of file\n+c\n\\ No newline at end of file\n")
        self.assertEqual(self.check(d, orig).patched_content, "a\nc")

    def test_form_feed_lines_not_split(self):
        orig = "a\x0cb\nc\n"
        r = self.check(diff("@@ -1,2 +1,2 @@\n a\x0cb\n-c\n+d\n"), orig)
        self.assertEqual(r.patched_content, "a\x0cb\nd\n")

    def test_context_mismatch_is_rejected(self):
        with self.assertRaises(PatchApplyError):
            self.check(diff("@@ -1,3 +1,3 @@\n a = 1\n-b = 999\n+b = 20\n c = 3\n"))

    def test_rejects_unsafe_shapes(self):
        cases = {
            "other file": diff("@@ -1 +1 @@\n-a = 1\n+a = 2\n", "other.py"),
            "create": "--- /dev/null\n+++ b/m.py\n@@ -0,0 +1 @@\n+x\n",
            "delete": "--- a/m.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-a = 1\n",
            "rename": "rename from m.py\nrename to n.py\n" + diff("@@ -1 +1 @@\n-a = 1\n+a = 2\n"),
            "mode": "new mode 100755\n" + diff("@@ -1 +1 @@\n-a = 1\n+a = 2\n"),
            "binary": "Binary files a/m.py and b/m.py differ\n",
            "multi-file": diff("@@ -1 +1 @@\n-a = 1\n+a = 2\n") + "--- a/n.py\n+++ b/n.py\n@@ -1 +1 @@\n-x\n+y\n",
            "no hunks": "--- a/m.py\n+++ b/m.py\n",
            "truncated": diff("@@ -1,3 +1,3 @@\n a = 1\n"),
            "bad counts": diff("@@ -1,1 +1,1 @@\n-a = 1\n-b = 2\n+x\n"),
            "empty": "  \n",
            "nul": diff("@@ -1 +1 @@\n-a = 1\n+a\x00\n"),
            "no-op hunk": diff("@@ -1,1 +1,1 @@\n a = 1\n"),
        }
        for name, d in cases.items():
            with self.subTest(name), self.assertRaises(PatchSafetyError):
                self.check(d)

    def test_protected_path_and_binary_original(self):
        with self.assertRaises(GuardrailViolation):
            self.check(diff("@@ -1 +1 @@\n-a = 1\n+a = 2\n", ".github/workflows/ci.yml"), path=".github/workflows/ci.yml")
        with self.assertRaises(PatchSafetyError):
            self.check(diff("@@ -1 +1 @@\n-a\n+b\n"), "a\x00\n")

    def test_flags_added_secret_but_not_preexisting(self):
        key = "ghp_" + "A" * 36
        r = self.check(diff(f"@@ -1,3 +1,3 @@\n a = 1\n-b = 2\n+b = '{key}'\n c = 3\n"))
        self.assertFalse(r.safe)
        self.assertEqual(r.secret_findings[0].rule, "github_token")
        self.assertNotIn(key, r.secret_findings[0].preview)
        orig = f"k = '{key}'\nb = 2\n"
        r2 = self.check(diff(f"@@ -1,2 +1,2 @@\n k = '{key}'\n-b = 2\n+b = 3\n"), orig)
        self.assertTrue(r2.safe)

    def test_size_limit(self):
        with self.assertRaises(PatchSafetyError):
            validate_single_file_patch(diff("@@ -1 +1 @@\n-a = 1\n+a = 22222\n"), expected_path="m.py",
                                       original_content="a = 1\n", max_bytes=5)


if __name__ == "__main__":
    unittest.main()
