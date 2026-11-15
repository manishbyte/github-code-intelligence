"""Encryption of GitHub tokens at rest (Fernet; comma-separated keys allow rotation)."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.exceptions import ConfigurationError, GitHubNotConnectedError


class TokenCipher:
    def __init__(self, keys: str) -> None:
        parts = [k.strip() for k in keys.split(",") if k.strip()]
        if not parts:
            raise ConfigurationError("GITHUB_TOKEN_ENCRYPTION_KEY is required.")
        try:
            self._fernet = MultiFernet([Fernet(k.encode("ascii")) for k in parts])
        except (ValueError, TypeError):
            raise ConfigurationError("GITHUB_TOKEN_ENCRYPTION_KEY is not a valid Fernet key.") from None

    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode("ascii")

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError):
            raise GitHubNotConnectedError("The stored GitHub token cannot be read; please reconnect GitHub.") from None
