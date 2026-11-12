"""Shared test fixtures. No live Telegram calls — the fetcher is always faked."""
from __future__ import annotations

import os
import sys

import pytest

# Make the project root importable (so `import app...` works from anywhere).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.ratelimit import RateLimiter  # noqa: E402
from app.telegram_client import DocumentInfo  # noqa: E402

TEST_SIGNING_KEY = "test-signing-key-do-not-use-in-production"


class FakeDocument:
    """A stand-in for a Telegram document: fixed bytes, no network."""

    def __init__(self, filename: str, size: int, chunks: list[bytes], fmt: str):
        self.filename = filename
        self.size = size
        self.chunks = chunks
        self.fmt = fmt


class FakeFetcher:
    """Fake TelegramFetcher: serves pre-registered documents, nothing else."""

    def __init__(self, docs: dict[tuple[str, int], FakeDocument]):
        self.docs = docs

    async def get_document(self, handle: str, post_id: int, fmt: str):
        doc = self.docs.get((handle, post_id))
        if doc is None or doc.fmt != fmt:
            return None
        return DocumentInfo(
            filename=doc.filename, size=doc.size, mime_type=None, document=doc
        )

    async def iter_file(self, document: FakeDocument, chunk_size: int = 65536):
        for chunk in document.chunks:
            yield chunk


@pytest.fixture()
def signing_key(monkeypatch):
    monkeypatch.setenv("PROXY_SIGNING_KEY", TEST_SIGNING_KEY)
    return TEST_SIGNING_KEY


@pytest.fixture()
def fresh_limiter(monkeypatch):
    """A fresh, generous rate limiter for the app under test."""
    import app.main as main

    monkeypatch.setattr(main, "_rate_limiter", RateLimiter(10_000))
    monkeypatch.setattr(main, "_fetcher", None)
    return main


@pytest.fixture()
def fake_book():
    """One fake EPUB: handle 'khazendar', post 12345, 3 chunks."""
    chunks = [b"PK\x03\x04" + b"A" * 100, b"B" * 200, b"C" * 50]
    doc = FakeDocument(
        filename="My Book - Author.epub",
        size=sum(len(c) for c in chunks),
        chunks=chunks,
        fmt="epub",
    )
    return ("khazendar", 12345, doc)


@pytest.fixture()
def client(monkeypatch, signing_key, fresh_limiter, fake_book):
    """TestClient with a fake fetcher serving one known book."""
    import app.main as main
    from fastapi.testclient import TestClient

    handle, post_id, doc = fake_book
    fake = FakeFetcher({(handle, post_id): doc})
    monkeypatch.setattr(main, "get_fetcher", lambda: fake)
    return TestClient(main.app)
