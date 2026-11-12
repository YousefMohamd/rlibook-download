"""Configuration — read from environment variables only.

No secret is ever hard-coded. On Fly.io these are set with
`fly secrets set ...` (see DEPLOY_GUIDE.md).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    """All settings. Read fresh from the environment on every call so tests
    can change env vars with monkeypatch.setenv."""

    signing_key: str | None
    telegram_api_id: str | None
    telegram_api_hash: str | None
    telegram_session_string: str | None
    token_ttl_seconds: int
    chunk_size: int
    rate_limit_per_minute: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            signing_key=os.environ.get("PROXY_SIGNING_KEY") or None,
            telegram_api_id=os.environ.get("TELEGRAM_API_ID") or None,
            telegram_api_hash=os.environ.get("TELEGRAM_API_HASH") or None,
            telegram_session_string=os.environ.get("TELEGRAM_SESSION_STRING") or None,
            token_ttl_seconds=_int("PROXY_TOKEN_TTL_SECONDS", 600),
            chunk_size=_int("PROXY_CHUNK_SIZE", 65536),
            rate_limit_per_minute=_int("PROXY_RATE_LIMIT_PER_MINUTE", 30),
        )


def get_settings() -> Settings:
    return Settings.from_env()
