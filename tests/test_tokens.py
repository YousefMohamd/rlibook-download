"""Token tests: valid / expired / tampered / mismatched / malformed."""
from __future__ import annotations

import pytest

from app.tokens import TokenError, make_token, verify_token
from tests.conftest import TEST_SIGNING_KEY

KEY = TEST_SIGNING_KEY
OTHER_KEY = "a-different-key"


def test_roundtrip():
    token = make_token(KEY, "khazendar", 12345, "epub", ttl_seconds=600, now=1_000_000)
    payload = verify_token(KEY, token, "khazendar", 12345, "epub", now=1_000_100)
    assert payload["h"] == "khazendar"
    assert payload["p"] == 12345
    assert payload["f"] == "epub"
    assert payload["exp"] == 1_000_600


def test_handle_normalised():
    token = make_token(KEY, "@Khazendar", 7, "pdf", now=1000)
    verify_token(KEY, token, "khazendar", 7, "pdf", now=1001)


def test_expired_token_refused():
    token = make_token(KEY, "khazendar", 1, "epub", ttl_seconds=10, now=1000)
    with pytest.raises(TokenError, match="expired"):
        verify_token(KEY, token, "khazendar", 1, "epub", now=1011)


def test_token_at_exact_expiry_refused():
    token = make_token(KEY, "khazendar", 1, "epub", ttl_seconds=10, now=1000)
    with pytest.raises(TokenError, match="expired"):
        verify_token(KEY, token, "khazendar", 1, "epub", now=1010)


def test_tampered_payload_refused():
    token = make_token(KEY, "khazendar", 1, "epub", now=1000)
    version, payload_b64, sig_b64 = token.split(".")
    # flip one character inside the payload part
    tampered = payload_b64[:-1] + ("A" if payload_b64[-1] != "A" else "B")
    with pytest.raises(TokenError):
        verify_token(KEY, f"{version}.{tampered}.{sig_b64}", "khazendar", 1, "epub", now=1001)


def test_tampered_signature_refused():
    token = make_token(KEY, "khazendar", 1, "epub", now=1000)
    version, payload_b64, sig_b64 = token.split(".")
    tampered = sig_b64[:-1] + ("A" if sig_b64[-1] != "A" else "B")
    with pytest.raises(TokenError):
        verify_token(KEY, f"{version}.{payload_b64}.{tampered}", "khazendar", 1, "epub", now=1001)


def test_wrong_key_refused():
    token = make_token(KEY, "khazendar", 1, "epub", now=1000)
    with pytest.raises(TokenError):
        verify_token(OTHER_KEY, token, "khazendar", 1, "epub", now=1001)


@pytest.mark.parametrize(
    "handle,post_id,fmt",
    [
        ("otherchannel", 1, "epub"),  # different channel
        ("khazendar", 999, "epub"),  # different post
        ("khazendar", 1, "pdf"),  # different format
    ],
)
def test_token_for_other_book_refused(handle, post_id, fmt):
    token = make_token(KEY, "khazendar", 1, "epub", now=1000)
    with pytest.raises(TokenError, match="does not match"):
        verify_token(KEY, token, handle, post_id, fmt, now=1001)


@pytest.mark.parametrize(
    "token",
    [
        None,
        "",
        "not-a-token",
        "v1.only-two-parts",
        "v2.abc.def",  # wrong version
        "v1.!!!.def",  # bad base64 payload
        "v1.abc.!!!",  # bad base64 signature
    ],
)
def test_malformed_tokens_refused(token):
    with pytest.raises(TokenError):
        verify_token(KEY, token, "khazendar", 1, "epub", now=1001)


def test_token_with_valid_json_but_no_fields_refused():
    import base64
    import hashlib
    import hmac

    payload_b64 = base64.urlsafe_b64encode(b"{}").rstrip(b"=").decode()
    sig_b64 = base64.urlsafe_b64encode(
        hmac.new(KEY.encode(), payload_b64.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    with pytest.raises(TokenError):
        verify_token(KEY, f"v1.{payload_b64}.{sig_b64}", "khazendar", 1, "epub", now=1001)
