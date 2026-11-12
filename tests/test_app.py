"""Endpoint tests with a mocked Telegram fetcher (no live calls)."""
from __future__ import annotations

import pytest

import app.main as main
from app.ratelimit import RateLimiter
from app.tokens import make_token
from tests.conftest import TEST_SIGNING_KEY, FakeDocument, FakeFetcher


def _token(handle="khazendar", post=12345, fmt="epub", ttl=600):
    return make_token(TEST_SIGNING_KEY, handle, post, fmt, ttl_seconds=ttl)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_index(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "rlibook-download-proxy"


def test_dl_no_token_refused(client):
    resp = client.get("/dl?h=khazendar&p=12345&f=epub")
    assert resp.status_code == 403
    assert "token" in resp.json()["detail"].lower()


def test_dl_expired_token_refused(client):
    resp = client.get(f"/dl?h=khazendar&p=12345&f=epub&t={_token(ttl=-10)}")
    assert resp.status_code == 403


def test_dl_tampered_token_refused(client):
    token = _token()
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    resp = client.get(f"/dl?h=khazendar&p=12345&f=epub&t={tampered}")
    assert resp.status_code == 403


def test_dl_token_for_other_book_refused(client):
    resp = client.get(f"/dl?h=khazendar&p=12345&f=epub&t={_token(post=999)}")
    assert resp.status_code == 403
    resp = client.get(f"/dl?h=khazendar&p=12345&f=epub&t={_token(fmt='pdf')}")
    assert resp.status_code == 403


def test_dl_valid_token_streams_file(client):
    resp = client.get(f"/dl?h=khazendar&p=12345&f=epub&t={_token()}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/epub+zip"
    assert resp.headers["content-disposition"] == 'attachment; filename="My Book - Author.epub"'
    assert resp.headers["content-length"] == str(100 + 4 + 200 + 50)
    assert resp.content == b"PK\x03\x04" + b"A" * 100 + b"B" * 200 + b"C" * 50


def test_dl_path_form(client):
    resp = client.get(f"/dl/khazendar/12345/epub?t={_token()}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/epub+zip"


def test_dl_token_in_bearer_header(client):
    resp = client.get(
        "/dl?h=khazendar&p=12345&f=epub",
        headers={"Authorization": f"Bearer {_token()}"},
    )
    assert resp.status_code == 200


def test_dl_unknown_format(client):
    resp = client.get(f"/dl?h=khazendar&p=12345&f=docx&t={_token(fmt='docx')}")
    assert resp.status_code == 400


def test_dl_bad_handle(client):
    resp = client.get(f"/dl?h=ab&p=12345&f=epub&t={_token(handle='ab')}")
    assert resp.status_code == 400
    resp = client.get(f"/dl?h=bad-handle!&p=12345&f=epub&t={_token(handle='bad-handle!')}")
    assert resp.status_code == 400


def test_dl_post_not_found(client):
    resp = client.get(f"/dl?h=khazendar&p=99999&f=epub&t={_token(post=99999)}")
    assert resp.status_code == 404


def test_dl_wrong_format_for_post(client):
    # the fake post has an EPUB, not a PDF
    resp = client.get(f"/dl?h=khazendar&p=12345&f=pdf&t={_token(fmt='pdf')}")
    assert resp.status_code == 404


def test_dl_no_signing_key_is_503(monkeypatch, fresh_limiter, fake_book):
    monkeypatch.delenv("PROXY_SIGNING_KEY", raising=False)
    from fastapi.testclient import TestClient

    handle, post_id, doc = fake_book
    monkeypatch.setattr(main, "get_fetcher", lambda: FakeFetcher({(handle, post_id): doc}))
    client = TestClient(main.app)
    resp = client.get("/dl?h=khazendar&p=12345&f=epub&t=whatever")
    assert resp.status_code == 503


def test_dl_no_telegram_credentials_is_503(monkeypatch, signing_key, fresh_limiter):
    """Valid token, but the fetcher cannot be built (no Telegram env vars)."""
    for var in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION_STRING"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(main, "_fetcher", None)
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    resp = client.get(f"/dl?h=khazendar&p=12345&f=epub&t={_token()}")
    assert resp.status_code == 503


def test_dl_rate_limited(monkeypatch, signing_key, fake_book):
    import app.main as main2
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main2, "_rate_limiter", RateLimiter(1))
    monkeypatch.setattr(main2, "_fetcher", None)
    handle, post_id, doc = fake_book
    monkeypatch.setattr(main2, "get_fetcher", lambda: FakeFetcher({(handle, post_id): doc}))
    client = TestClient(main2.app)
    first = client.get(f"/dl?h=khazendar&p=12345&f=epub&t={_token()}")
    assert first.status_code == 200
    second = client.get(f"/dl?h=khazendar&p=12345&f=epub&t={_token()}")
    assert second.status_code == 429


def test_dl_arabic_filename_header(client, monkeypatch, signing_key, fresh_limiter):
    import app.main as main2
    from fastapi.testclient import TestClient

    doc = FakeDocument(
        filename="القراءة المثمرة.epub", size=3, chunks=[b"abc"], fmt="epub"
    )
    monkeypatch.setattr(
        main2, "get_fetcher", lambda: FakeFetcher({("khazendar", 777): doc})
    )
    c = TestClient(main2.app)
    resp = c.get(f"/dl?h=khazendar&p=777&f=epub&t={_token(post=777)}")
    assert resp.status_code == 200
    assert "filename*=UTF-8''" in resp.headers["content-disposition"]
    assert resp.content == b"abc"
