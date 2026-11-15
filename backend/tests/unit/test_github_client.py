import json
import unittest

from app.integrations.github.client import GitHubClient, RawResponse
from app.integrations.github.exceptions import (
    ForbiddenOperationError, GitHubAuthError, GitHubNotFoundError, GitHubPermissionError,
    GitHubRateLimitError, GitHubServerError, GitHubTransportError, TransportFailure,
)

OK = RawResponse(200, {}, b'{"a": 1}')


class Scripted:
    def __init__(self, *items):
        self.items, self.calls = list(items), 0

    async def send(self, *a, **k):
        self.calls += 1
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def resp(status, body=None, headers=None):
    return RawResponse(status, headers or {}, json.dumps(body or {}).encode())


async def nosleep(_):
    return None


def client(t, **kw):
    return GitHubClient("secret-token-123", transport=t, sleep=nosleep, **kw)


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_allowlist_and_read_only(self):
        c = client(Scripted(OK))
        for method, path in [("GET", "/orgs/x"), ("GET", "/repos/o/r/../../user"), ("DELETE", "/repos/o/r"),
                             ("GET", "/repos/o/r/contents/%2e%2e/x"), ("GET", "/repos/o/r?x=1"),
                             ("GET", "https://evil.com/user"), ("POST", "/repos/o/r/issues")]:
            with self.subTest(path=path), self.assertRaises(ForbiddenOperationError):
                await c.request(method, path)
        self.assertEqual((await c.request("GET", "/user")).data, {"a": 1})

    async def test_write_client_allows_only_listed_writes(self):
        c = client(Scripted(resp(201, {"x": 1})), allow_writes=True)
        await c.request("POST", "/repos/o/r/issues", json_body={"title": "t"})
        with self.assertRaises(ForbiddenOperationError):
            await c.request("PUT", "/repos/o/r/issues")
        with self.assertRaises(ForbiddenOperationError):
            await c.request("PATCH", "/repos/o/r/pulls/1")

    async def test_get_retries_server_errors_but_writes_do_not(self):
        t = Scripted(resp(502), resp(503), OK)
        self.assertEqual((await client(t).request("GET", "/user")).status, 200)
        self.assertEqual(t.calls, 3)
        t = Scripted(resp(500), resp(500), resp(500))
        with self.assertRaises(GitHubServerError):
            await client(t).request("GET", "/user")
        self.assertEqual(t.calls, 3)
        t = Scripted(resp(500), OK)
        with self.assertRaises(GitHubServerError):
            await client(t, allow_writes=True).request("POST", "/repos/o/r/issues", json_body={})
        self.assertEqual(t.calls, 1)

    async def test_transport_failure_and_outcome_unknown(self):
        with self.assertRaises(GitHubTransportError) as cm:
            await client(Scripted(*[TransportFailure("Timeout")] * 3)).request("GET", "/user")
        self.assertFalse(cm.exception.outcome_unknown)
        with self.assertRaises(GitHubTransportError) as cm:
            await client(Scripted(TransportFailure("Timeout")), allow_writes=True).request(
                "POST", "/repos/o/r/issues", json_body={})
        self.assertTrue(cm.exception.outcome_unknown)

    async def test_error_mapping(self):
        cases = [(401, GitHubAuthError), (404, GitHubNotFoundError), (403, GitHubPermissionError)]
        for status, exc in cases:
            with self.subTest(status=status), self.assertRaises(exc):
                await client(Scripted(resp(status, {"message": "x"}))).request("GET", "/user")

    async def test_rate_limit_waits_then_succeeds_or_raises(self):
        slept = []

        async def sleep(s):
            slept.append(s)

        c = GitHubClient("tok", transport=Scripted(resp(403, {"message": "rate limit"}, {"retry-after": "2"}), OK), sleep=sleep)
        await c.request("GET", "/user")
        self.assertEqual(slept, [2.0])
        c = GitHubClient("tok", transport=Scripted(resp(429, {}, {"retry-after": "9999"})), sleep=sleep)
        with self.assertRaises(GitHubRateLimitError) as cm:
            await c.request("GET", "/user")
        self.assertEqual(cm.exception.retry_after, 9999.0)
        c = GitHubClient("tok", transport=Scripted(resp(403, {"message": "x"}, {"x-ratelimit-remaining": "0"})),
                         sleep=sleep, max_retries=0)
        with self.assertRaises(GitHubRateLimitError):
            await c.request("GET", "/user")


if __name__ == "__main__":
    unittest.main()
