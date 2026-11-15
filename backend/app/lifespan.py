"""Application startup/shutdown: engine, shared HTTP transport, cipher and LLM client."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.agents.llm import GroqClient
from app.core.logging import configure_logging
from app.core.token_encryption import TokenCipher
from app.database.connection import create_engine, create_session_factory
from app.integrations.github.client import HttpxTransport

logger = logging.getLogger("app.lifespan")


def build_cipher(keys: str, *, production: bool) -> TokenCipher:
    if keys:
        return TokenCipher(keys)
    if production:
        raise RuntimeError("GITHUB_TOKEN_ENCRYPTION_KEY is required in production.")
    logger.warning("No GITHUB_TOKEN_ENCRYPTION_KEY set; using an ephemeral key (stored GitHub tokens become unreadable on restart).")
    return TokenCipher(TokenCipher.generate_key())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = app.state.settings
    configure_logging(settings.log_level)
    engine = create_engine(settings)
    transport = HttpxTransport()
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.transport = transport
    app.state.cipher = build_cipher(settings.github_token_encryption_key, production=settings.is_production)
    app.state.llm = (
        GroqClient(settings.groq_api_key, settings.groq_model, transport)
        if settings.groq_api_key and settings.groq_model else None
    )
    if app.state.llm is None:
        logger.warning("GROQ_API_KEY/GROQ_MODEL not set; AI features are disabled.")
    try:
        yield
    finally:
        await transport.aclose()
        await engine.dispose()
