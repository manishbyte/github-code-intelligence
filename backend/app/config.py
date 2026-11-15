
"""Environment-driven settings, validated at startup. Secrets are never printed."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urlsplit

from dotenv import load_dotenv
from app.core.exceptions import ConfigurationError

load_dotenv()

_ENVS = {"development", "test", "production"}
_PLACEHOLDERS = {"", "replace_with_secure_random_value", "changeme"}


def _int(env: Mapping[str, str], name: str, default: int, problems: list[str]) -> int:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        problems.append(f"{name} must be an integer")
        return default
    if value <= 0:
        problems.append(f"{name} must be positive")
    return value


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    app_debug: bool
    app_base_url: str
    frontend_base_url: str
    database_url: str
    github_client_id: str
    github_callback_url: str
    groq_model: str
    access_token_expire_minutes: int
    refresh_token_expire_days: int
    max_source_file_bytes: int
    max_review_input_tokens: int
    log_level: str
    app_secret_key: str = field(repr=False)
    github_client_secret: str = field(repr=False)
    github_token_encryption_key: str = field(repr=False)
    groq_api_key: str = field(repr=False)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        problems: list[str] = []

        def get(key: str, default: str = "") -> str:
            return env.get(key, default).strip()

        app_env = get("APP_ENV", "development")
        if app_env not in _ENVS:
            problems.append("APP_ENV must be development, test or production")

        prod = app_env == "production"
        debug = get("APP_DEBUG", "false").lower() in {"1", "true", "yes"}
        allow_insecure_http = get("ALLOW_INSECURE_HTTP", "false").lower() in {
            "1", "true", "yes"
        }

        secret = get("APP_SECRET_KEY")
        if secret in _PLACEHOLDERS or len(secret) < (32 if prod else 16):
            problems.append(
                "APP_SECRET_KEY must be a random value"
                + (" of at least 32 characters" if prod else "")
            )

        url_defaults = {
            "APP_BASE_URL": "http://localhost:8008",
            "FRONTEND_BASE_URL": "http://localhost:8502",
            "GITHUB_CALLBACK_URL": (
                "http://localhost:8008/api/v1/github/oauth/callback"
            ),
        }

        for name, default in url_defaults.items():
            value = get(name, default)
            parsed = urlsplit(value)

            valid_scheme = parsed.scheme in {"http", "https"}
            valid_host = bool(parsed.hostname)
            requires_https = prod and not allow_insecure_http

            if (
                not valid_scheme
                or not valid_host
                or (requires_https and parsed.scheme != "https")
            ):
                requirement = (
                    "https" if requires_https else "a valid http(s)"
                )
                problems.append(f"{name} must be {requirement} URL")

        if prod and debug:
            problems.append("APP_DEBUG must be false in production")

        if not get("DATABASE_URL").startswith("postgresql+asyncpg://"):
            problems.append(
                "DATABASE_URL must be a postgresql+asyncpg:// URL"
            )

        required = (
            "GITHUB_CLIENT_ID",
            "GITHUB_CLIENT_SECRET",
            "GITHUB_TOKEN_ENCRYPTION_KEY",
            "GROQ_API_KEY",
            "GROQ_MODEL",
        )

        if prod:
            problems += [
                f"{name} is required in production"
                for name in required
                if not get(name)
            ]

        settings = cls(
            app_name=get("APP_NAME", "GitHub Code Intelligence"),
            app_env=app_env,
            app_debug=debug,
            app_base_url=get("APP_BASE_URL", url_defaults["APP_BASE_URL"]),
            frontend_base_url=get(
                "FRONTEND_BASE_URL", url_defaults["FRONTEND_BASE_URL"]
            ),
            database_url=get("DATABASE_URL"),
            github_client_id=get("GITHUB_CLIENT_ID"),
            github_callback_url=get(
                "GITHUB_CALLBACK_URL", url_defaults["GITHUB_CALLBACK_URL"]
            ),
            groq_model=get("GROQ_MODEL"),
            access_token_expire_minutes=_int(
                env, "ACCESS_TOKEN_EXPIRE_MINUTES", 15, problems
            ),
            refresh_token_expire_days=_int(
                env, "REFRESH_TOKEN_EXPIRE_DAYS", 7, problems
            ),
            max_source_file_bytes=_int(
                env, "MAX_SOURCE_FILE_BYTES", 500_000, problems
            ),
            max_review_input_tokens=_int(
                env, "MAX_REVIEW_INPUT_TOKENS", 20_000, problems
            ),
            log_level=get("LOG_LEVEL", "INFO").upper(),
            app_secret_key=secret,
            github_client_secret=get("GITHUB_CLIENT_SECRET"),
            github_token_encryption_key=get("GITHUB_TOKEN_ENCRYPTION_KEY"),
            groq_api_key=get("GROQ_API_KEY"),
        )

        if problems:
            raise ConfigurationError(
                "Invalid configuration: " + "; ".join(sorted(set(problems)))
            )

        return settings
