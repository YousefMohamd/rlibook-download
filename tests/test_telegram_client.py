"""Regression test for the lazy-Telegram-client name collision.

Bug (found live 2026-11-15): ``TelegramFetcher`` defined BOTH an instance
attribute ``self._client = None`` (``__init__``) AND a method
``async def _client(self)``. The instance attribute shadows the method, so
every ``/dl`` request died with ``TypeError: 'NoneType' object is not
callable`` at ``client = await self._client()`` — the proxy returned 500
for every download even though the signing key and token were valid.

The fix renames the method to ``_get_client`` (the attribute stays
``self._client``). This test exercises the REAL fetcher (not the FakeFetcher
in conftest — that is exactly why the bug shipped: the suite never touched
the real lazy-client path). No network: Telethon is faked in sys.modules.
"""

from __future__ import annotations

import sys
import types

import pytest

from app.telegram_client import TelegramFetcher


class FakeTelegramClient:
    """Stand-in for Telethon's TelegramClient: records calls, no network."""

    instances: list["FakeTelegramClient"] = []

    def __init__(self, session, api_id, api_hash):
        self.session = session
        self.api_id = api_id
        self.api_hash = api_hash
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.messages_to_return = None  # get_messages returns this
        FakeTelegramClient.instances.append(self)

    async def connect(self):
        self.connect_calls += 1

    async def disconnect(self):
        self.disconnect_calls += 1

    async def get_messages(self, handle, ids=None):
        return self.messages_to_return

    async def iter_download(self, document, chunk_size=65536):
        for chunk in getattr(document, "chunks", [b"fake-bytes"]):
            yield chunk


class FakeStringSession:
    """Stand-in for telethon.sessions.StringSession."""

    def __init__(self, value):
        self.value = value


@pytest.fixture()
def fake_telethon(monkeypatch):
    """Inject a fake `telethon` package so the lazy import gets our stub."""
    telethon = types.ModuleType("telethon")
    telethon.TelegramClient = FakeTelegramClient
    sessions = types.ModuleType("telethon.sessions")
    sessions.StringSession = FakeStringSession
    telethon.sessions = sessions
    monkeypatch.setitem(sys.modules, "telethon", telethon)
    monkeypatch.setitem(sys.modules, "telethon.sessions", sessions)
    FakeTelegramClient.instances.clear()
    return telethon


@pytest.mark.asyncio()
async def test_get_document_missing_post_returns_none_not_typeerror(fake_telethon):
    """The regression: get_document must NOT raise TypeError.

    Before the fix this raised ``TypeError: 'NoneType' object is not
    callable`` (the instance attribute shadowed the method). Now it must
    return None for a missing post.
    """
    fetcher = TelegramFetcher("12345", "fake-hash", "1fake-session-string")
    result = await fetcher.get_document("khazendar", 99999999, "epub")
    assert result is None
    # And the lazy client was actually created + connected exactly once.
    assert len(FakeTelegramClient.instances) == 1
    assert FakeTelegramClient.instances[0].connect_calls == 1


@pytest.mark.asyncio()
async def test_lazy_client_is_a_singleton(fake_telethon):
    """A second call reuses the same client (connect is not repeated)."""
    fetcher = TelegramFetcher("12345", "fake-hash", "1fake-session-string")
    await fetcher.get_document("khazendar", 1, "epub")
    await fetcher.get_document("khazendar", 2, "epub")
    assert len(FakeTelegramClient.instances) == 1
    assert FakeTelegramClient.instances[0].connect_calls == 1


@pytest.mark.asyncio()
async def test_close_disconnects_and_resets(fake_telethon):
    """close() disconnects, and the next call builds a fresh client."""
    fetcher = TelegramFetcher("12345", "fake-hash", "1fake-session-string")
    await fetcher.get_document("khazendar", 1, "epub")
    first = FakeTelegramClient.instances[0]
    await fetcher.close()
    assert first.disconnect_calls == 1
    assert fetcher._client is None
    await fetcher.get_document("khazendar", 1, "epub")
    assert len(FakeTelegramClient.instances) == 2
