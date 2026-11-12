"""RliBook download proxy — FastAPI app.

Endpoints
---------
GET /health
    Liveness check. No credentials needed. {"ok": true}

GET /dl?h=<handle>&p=<post_id>&f=<format>&t=<token>
GET /dl/<handle>/<post_id>/<format>?t=<token>
    Download one book file. The token (query param `t`, or
    `Authorization: Bearer <token>`) must be a valid HMAC token for exactly
    this book (see app/tokens.py). The file is streamed from the Telegram
    channel post to the browser — never written to disk.

    Errors (JSON {"detail": ...}):
      400  bad handle / post id / unknown format
      403  missing, malformed, tampered, expired, or mismatched token
      404  no book file in that format on that post
      429  too many download requests from this IP
      502  Telegram fetch failed
      503  proxy not configured (no signing key / no Telegram credentials)

Run locally:
    uvicorn app.main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import re

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from . import tokens
from .formats import ALLOWED_FORMATS, content_disposition, mime_for, safe_filename
from .ratelimit import RateLimiter, client_ip
from .settings import get_settings
from .telegram_client import TelegramConfigError, TelegramFetcher, TelegramFetchError

app = FastAPI(
    title="RliBook download proxy",
    description="Streams a book file from a Telegram channel post to the browser. "
    "No storage, HMAC-token protected, legal (PD/CC) books only.",
    version="1.0.0",
)

# Telegram handles: 5-32 chars, letters/digits/underscore.
_HANDLE_RE = re.compile(r"^[a-z0-9_]{5,32}$")

# Module-level singletons (tests replace them).
_rate_limiter: RateLimiter | None = None
_fetcher: TelegramFetcher | None = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(get_settings().rate_limit_per_minute)
    return _rate_limiter


def get_fetcher() -> TelegramFetcher:
    """Lazy singleton. Raises TelegramConfigError when credentials are missing."""
    global _fetcher
    if _fetcher is None:
        settings = get_settings()
        if not (
            settings.telegram_api_id
            and settings.telegram_api_hash
            and settings.telegram_session_string
        ):
            raise TelegramConfigError(
                "Telegram credentials are not configured "
                "(TELEGRAM_API_ID / TELEGRAM_API_HASH / TELEGRAM_SESSION_STRING)"
            )
        _fetcher = TelegramFetcher(
            settings.telegram_api_id,
            settings.telegram_api_hash,
            settings.telegram_session_string,
        )
    return _fetcher


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": message})


def _extract_token(request: Request, t: str | None) -> str | None:
    if t:
        return t
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def _validate_handle(handle: str) -> str | None:
    """Normalised handle, or None when it is not a plausible Telegram handle."""
    handle = tokens.normalize_handle(handle)
    return handle if _HANDLE_RE.match(handle) else None


async def _download(request: Request, handle: str, post_id: int, fmt: str, t: str | None):
    settings = get_settings()
    fmt = (fmt or "").strip().lower()

    # 1. Parameters -------------------------------------------------------
    handle = _validate_handle(handle)
    if handle is None:
        return _error(400, "invalid channel handle")
    if post_id is None or int(post_id) <= 0:
        return _error(400, "invalid post id")
    post_id = int(post_id)
    if fmt not in ALLOWED_FORMATS:
        return _error(400, f"unknown format: {fmt!r} (allowed: {sorted(ALLOWED_FORMATS)})")

    # 2. Rate limit (per IP, requests only — one download is one request) --
    if not get_rate_limiter().allow(client_ip(request)):
        return _error(429, "too many download requests, please try again shortly")

    # 3. Signing key must exist -------------------------------------------
    if not settings.signing_key:
        return _error(503, "download proxy is not configured (no signing key)")

    # 4. Token: the website only issues one for a non-flagged book --------
    token = _extract_token(request, t)
    try:
        tokens.verify_token(settings.signing_key, token, handle, post_id, fmt)
    except tokens.TokenError as exc:
        # Deliberately one status for every token problem: no oracle.
        return _error(403, f"download refused: {exc}")

    # 5. Telegram: find the document --------------------------------------
    try:
        fetcher = get_fetcher()
    except TelegramConfigError as exc:
        return _error(503, str(exc))
    try:
        doc = await fetcher.get_document(handle, post_id, fmt)
    except TelegramFetchError as exc:
        return _error(502, f"could not fetch the book from Telegram: {exc}")
    if doc is None:
        return _error(404, "no book file in this format on that post")

    # 6. Stream it — never written to disk --------------------------------
    filename = safe_filename(doc.filename, post_id, fmt)
    headers = {"Content-Disposition": content_disposition(filename)}
    if doc.size:
        headers["Content-Length"] = str(doc.size)

    async def _stream():
        async for chunk in fetcher.iter_file(doc.document, chunk_size=settings.chunk_size):
            yield chunk

    return StreamingResponse(
        _stream(), media_type=mime_for(fmt), headers=headers
    )


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/")
async def index():
    return {
        "service": "rlibook-download-proxy",
        "ok": True,
        "endpoints": {
            "health": "GET /health",
            "download": "GET /dl?h=<handle>&p=<post_id>&f=<format>&t=<token>",
        },
        "formats": sorted(ALLOWED_FORMATS),
    }


@app.get("/dl")
async def download_query(
    request: Request,
    h: str = Query(..., description="channel handle, e.g. khazendar"),
    p: int = Query(..., description="post id in the channel"),
    f: str = Query(..., description="format: epub, pdf, mobi, azw3, kfx, txt"),
    t: str | None = Query(None, description="HMAC download token"),
):
    return await _download(request, h, p, f, t)


@app.get("/dl/{handle}/{post_id}/{fmt}")
async def download_path(
    request: Request,
    handle: str,
    post_id: int,
    fmt: str,
    t: str | None = Query(None, description="HMAC download token"),
):
    return await _download(request, handle, post_id, fmt, t)
