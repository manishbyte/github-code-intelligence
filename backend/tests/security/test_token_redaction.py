import json
import pickle
import unittest

from app.guardrails.secret_detection import find_secrets, find_secrets_in_added_lines, redact_secrets
from app.integrations.github.client import GitHubClient, RawResponse
from app.integrations.github.exceptions import GitHubPermissionError

TOKEN = "ghp_" + "Z" * 36


class Echo:
    async def send(self, *a, **k):
        return RawResponse(403, {}, json.dumps({"message": f"bad credentials {TOKEN} here"}).encode())


class TokenTests(unittest.IsolatedAsyncioTestCase):
    def test_repr_and_pickle_do_not_leak(self):
        c = GitHubClient(TOKEN, transport=Echo())
        self.assertNotIn(TOKEN, repr(c))
        with self.assertRaises(TypeError):
            pickle.dumps(c)

    async def test_error_messages_scrub_token(self):
        c = GitHubClient(TOKEN, transport=Echo())
        with self.assertRaises(GitHubPermissionError) as cm:
            await c.request("GET", "/user")
        self.assertNotIn(TOKEN, str(cm.exception))
        self.assertNotIn(TOKEN, repr(cm.exception.details))

    def test_invalid_tokens_rejected(self):
        for bad in ("", "a b", "tok\nen"):
            with self.assertRaises(ValueError):
                GitHubClient(bad, transport=Echo())

    def test_secret_detection_and_redaction(self):
        text = f'token = "{TOKEN}"\nAWS=AKIAABCDEFGHIJKLMNOP\npassword = "changeme-example-value"\n-----BEGIN RSA PRIVATE KEY-----\n'
        rules = {f.rule for f in find_secrets(text)}
        self.assertEqual(rules, {"github_token", "aws_access_key_id", "private_key_block", "hardcoded_credential"})
        for f in find_secrets(text):
            self.assertLessEqual(len(f.preview), 8)
        red = redact_secrets(text)
        self.assertNotIn(TOKEN, red)
        self.assertNotIn("AKIAABCDEFGHIJKLMNOP", red)
        self.assertEqual(red.count("\n"), text.count("\n"))

    def test_placeholders_not_flagged_and_added_only(self):
        self.assertEqual(find_secrets('api_key = "your_api_key_here_please"'), [])
        self.assertTrue(find_secrets('api_key = "q8Zr2LmP0xVb7TnA"'))
        old = f"x = '{TOKEN}'\n"
        self.assertEqual(find_secrets_in_added_lines(old, old + "y = 1\n"), [])
        self.assertEqual(len(find_secrets_in_added_lines("y = 1\n", old + "y = 1\n")), 1)


if __name__ == "__main__":
    unittest.main()
