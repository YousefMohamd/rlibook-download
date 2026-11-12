"""HMAC-signed download tokens.

Token scheme (version "v1")
---------------------------
A token proves that the website checked the book and found it NOT flagged
(public-domain / Creative Commons). The proxy trusts the token — it never
serves a book without one.

    token = "v1" "." payload_b64 "." signature_b64

    payload = {"h": "<channel handle, lower-case, no @>",
               "p": <post id, int>,
               "f": "<format, e.g. epub>",
               "exp": <unix expiry, int>}
    payload_b64   = base64url(JSON(payload))          # sorted keys, no spaces
    signature_b64 = base64url(HMAC-SHA256(signing_key, payload_b64))

Verification (verify_token):
  1. shape is v1.<b64>.<b64>
  2. signature matches (hmac.compare_digest — constant time)
  3. payload decodes to a dict with h / p / f / exp
  4. h, p, f match EXACTLY the book being requested
  5. exp is in the future (token not expired)

The signing key lives only in the environment (PROXY_SIGNING_KEY) — on the
proxy (Fly.io secret) and on the token issuer (a Cloudflare Pages Function /
Worker on the website side — a later step, NOT part of this service).
The key is never in the code, never in the repo, never in the browser.

The website issues a token when it renders a download button, with a short
TTL (default 600 s = 10 min). A token is single-book: it cannot be reused
for a different channel, post, or format.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

VERSION = "v1"
DEFAULT_TTL_SECONDS = 600


class TokenError(Exception):
    """Raised when a token is missing, malformed, tampered, or expired."""


def normalize_handle(handle: str) -> str:
    """Telegram channel handle: lower-case, no leading @."""
    return (handle or "").strip().lstrip("@").lower()


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def make_token(
    signing_key: str,
    handle: str,
    post_id: int,
    fmt: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: int | None = None,
) -> str:
    """Create a signed token for one book (handle, post_id, format)."""
    now = int(time.time()) if now is None else int(now)
    payload = {
        "h": normalize_handle(handle),
        "p": int(post_id),
        "f": (fmt or "").strip().lower(),
        "exp": now + int(ttl_seconds),
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64url_encode(payload_json)
    sig = hmac.new(
        signing_key.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{VERSION}.{payload_b64}.{_b64url_encode(sig)}"


def verify_token(
    signing_key: str,
    token: str | None,
    handle: str,
    post_id: int,
    fmt: str,
    now: int | None = None,
) -> dict:
    """Verify that `token` authorises exactly this book.

    Returns the decoded payload on success, raises TokenError otherwise.
    """
    now = int(time.time()) if now is None else int(now)
    if not token or not isinstance(token, str):
        raise TokenError("missing download token")
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != VERSION:
        raise TokenError("malformed download token")
    _, payload_b64, sig_b64 = parts

    expected_sig = hmac.new(
        signing_key.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).digest()
    try:
        given_sig = _b64url_decode(sig_b64)
    except Exception:
        raise TokenError("malformed download token")
    if not hmac.compare_digest(expected_sig, given_sig):
        raise TokenError("bad download token signature")

    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception:
        raise TokenError("malformed download token")
    if not isinstance(payload, dict):
        raise TokenError("malformed download token")

    if (
        payload.get("h") != normalize_handle(handle)
        or payload.get("p") != int(post_id)
        or payload.get("f") != (fmt or "").strip().lower()
    ):
        raise TokenError("download token does not match this book")

    exp = payload.get("exp")
    if not isinstance(exp, int) or exp <= now:
        raise TokenError("download token expired")

    return payload
