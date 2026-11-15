import json
import unittest
from urllib.parse import parse_qs, urlsplit

from app.integrations.github.client import RawResponse
from app.integrations.github.exceptions import GitHubAuthError
from app.integrations.github.oauth import build_authorize_url, exchange_code, revoke_grant


class Recorder:
    def __init__(self, response):
        self.response, self.calls = response, []

    async def send(self, method, url, *, headers, params, json_body, timeout):
        self.calls.append((method, url, dict(headers), json_body))
        return self.response


def resp(status, body=None):
    return RawResponse(status, {}, json.dumps(body or {}).encode())


class AuthorizeUrlTests(unittest.TestCase):
    def query(self, access):
        url = build_authorize_url(client_id="cid", redirect_uri="http://localhost:8000/cb", state="st", access=access)
        return urlsplit(url), parse_qs(urlsplit(url).query)

    def test_read_requests_no_scope(self):
        parts, q = self.query("read")
        self.assertEqual((parts.netloc, parts.path), ("github.com", "/login/oauth/authorize"))
        self.assertNotIn("scope", q)
        self.assertEqual((q["client_id"], q["state"]), (["cid"], ["st"]))

    def test_write_requests_only_public_repo(self):
        self.assertEqual(self.query("write")[1]["scope"], ["public_repo"])


class ExchangeTests(unittest.IsolatedAsyncioTestCase):
    async def exchange(self, response):
        t = Recorder(response)
        token = await exchange_code(t, client_id="cid", client_secret="sec", code="c", redirect_uri="http://x/cb")
        return token, t

    async def test_success_parses_scopes_and_posts_json(self):
        token, t = await self.exchange(resp(200, {"access_token": "gho_x", "scope": "public_repo,read:user", "token_type": "bearer"}))
        self.assertEqual((token.access_token, token.scopes), ("gho_x", ("public_repo", "read:user")))
        method, url, headers, body = t.calls[0]
        self.assertEqual((method, url, headers["Accept"]), ("POST", "https://github.com/login/oauth/access_token", "application/json"))
        self.assertEqual(body["code"], "c")

    async def test_error_payloads_are_rejected_without_leaking_details(self):
        for response in (resp(200, {"error": "bad_verification_code", "error_description": "secret details"}), resp(500), resp(200, {})):
            with self.assertRaises(GitHubAuthError) as cm:
                await self.exchange(response)
            self.assertNotIn("secret details", str(cm.exception))

    async def test_revoke_grant(self):
        t = Recorder(resp(204))
        self.assertTrue(await revoke_grant(t, client_id="cid", client_secret="sec", access_token="gho_x"))
        method, url, headers, body = t.calls[0]
        self.assertEqual((method, url), ("DELETE", "https://api.github.com/applications/cid/grant"))
        self.assertTrue(headers["Authorization"].startswith("Basic "))
        self.assertEqual(body, {"access_token": "gho_x"})
        self.assertFalse(await revoke_grant(Recorder(resp(500)), client_id="cid", client_secret="sec", access_token="t"))


if __name__ == "__main__":
    unittest.main()
