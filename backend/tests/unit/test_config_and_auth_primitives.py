import unittest
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.core.exceptions import AuthenticationError, ConfigurationError, InvalidInputError
from app.core.password import hash_password, needs_rehash, verify_password
from app.core.security import create_token, decode_token, generate_opaque_token, hash_token
import base64
import json

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
DEV = {"APP_SECRET_KEY": "x" * 24, "DATABASE_URL": "postgresql+asyncpg://u:p@db:5432/app"}
PROD = {**DEV, "APP_ENV": "production", "APP_SECRET_KEY": "s" * 40, "APP_BASE_URL": "https://api.example.com",
        "FRONTEND_BASE_URL": "https://app.example.com", "GITHUB_CALLBACK_URL": "https://api.example.com/cb",
        "GITHUB_CLIENT_ID": "id", "GITHUB_CLIENT_SECRET": "sec", "GITHUB_TOKEN_ENCRYPTION_KEY": "k",
        "GROQ_API_KEY": "g", "GROQ_MODEL": "m"}


class ConfigTests(unittest.TestCase):
    def test_dev_defaults_and_redaction(self):
        s = Settings.from_env(DEV)
        self.assertEqual((s.app_env, s.access_token_expire_minutes, s.max_source_file_bytes), ("development", 15, 500_000))
        self.assertNotIn("x" * 24, repr(s))

    def test_invalid_values(self):
        for override in ({"APP_SECRET_KEY": "replace_with_secure_random_value"}, {"APP_ENV": "staging"},
                         {"DATABASE_URL": "sqlite:///x"}, {"MAX_SOURCE_FILE_BYTES": "abc"}, {"ACCESS_TOKEN_EXPIRE_MINUTES": "0"}):
            with self.subTest(override=override), self.assertRaises(ConfigurationError):
                Settings.from_env({**DEV, **override})

    def test_production_is_strict(self):
        self.assertTrue(Settings.from_env(PROD).is_production)
        for override in ({"APP_DEBUG": "true"}, {"GROQ_API_KEY": ""}, {"APP_SECRET_KEY": "short" * 3},
                         {"APP_BASE_URL": "http://api.example.com"}, {"GITHUB_TOKEN_ENCRYPTION_KEY": ""}):
            with self.subTest(override=override), self.assertRaises(ConfigurationError) as cm:
                Settings.from_env({**PROD, **override})
            self.assertNotIn("s" * 40, str(cm.exception))


class PasswordTests(unittest.TestCase):
    def test_hash_and_verify(self):
        h = hash_password("correct horse battery")
        self.assertTrue(verify_password("correct horse battery", h))
        self.assertFalse(verify_password("wrong horse battery!", h))
        self.assertNotEqual(h, hash_password("correct horse battery"))  # unique salt
        self.assertFalse(needs_rehash(h))

    def test_policy_and_malformed_hashes(self):
        for bad in ("short", "aaaaaaaaaaaaaaaa", " " * 14):
            with self.assertRaises(InvalidInputError):
                hash_password(bad)
        for stored in ("", "bcrypt$x", "scrypt$1$2$3$x$y", "garbage"):
            self.assertFalse(verify_password("whatever-password", stored))


class TokenTests(unittest.TestCase):
    def test_roundtrip_and_claims(self):
        t = create_token("k" * 32, subject="u1", token_type="access", ttl_seconds=60, now=NOW)
        c = decode_token("k" * 32, t, expected_type="access", now=NOW)
        self.assertEqual((c["sub"], c["typ"]), ("u1", "access"))

    def test_rejections(self):
        t = create_token("k" * 32, subject="u1", token_type="access", ttl_seconds=60, now=NOW)
        cases = {
            "expired": lambda: decode_token("k" * 32, t, expected_type="access", now=NOW + timedelta(seconds=60)),
            "wrong type": lambda: decode_token("k" * 32, t, expected_type="refresh", now=NOW),
            "wrong key": lambda: decode_token("z" * 32, t, expected_type="access", now=NOW),
            "tampered": lambda: decode_token("k" * 32, t[:-2] + "AA", expected_type="access", now=NOW),
            "garbage": lambda: decode_token("k" * 32, "a.b", expected_type="access", now=NOW),
        }
        h, p, _ = t.split(".")
        none_header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
        cases["alg none"] = lambda: decode_token("k" * 32, f"{none_header}.{p}.", expected_type="access", now=NOW)
        for name, fn in cases.items():
            with self.subTest(name), self.assertRaises(AuthenticationError):
                fn()

    def test_opaque_tokens(self):
        a, b = generate_opaque_token(), generate_opaque_token()
        self.assertNotEqual(a, b)
        self.assertEqual(len(hash_token(a)), 64)
        self.assertNotIn(a, hash_token(a))


if __name__ == "__main__":
    unittest.main()
