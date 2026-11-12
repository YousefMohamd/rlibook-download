"""Tiny in-memory per-IP rate limiter (sliding window).

Purpose: protect the Fly.io bandwidth allowance from a runaway client or a
shared token being hammered. It limits *requests* to /dl, not bytes — one
download is one request no matter how big the file is.

Default: 30 download requests per minute per IP (configurable with
PROXY_RATE_LIMIT_PER_MINUTE; 0 disables it). This is generous for humans
and cheap to enforce. It is NOT a security boundary — the HMAC token is.
"""
from __future__ import annotations

import time
from collections import defaultdict


class RateLimiter:
    def __init__(self, per_minute: int, now_fn=time.time):
        self.per_minute = int(per_minute)
        self._now = now_fn
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str) -> bool:
        """True if `key` may proceed, False if it is over the limit."""
        if self.per_minute <= 0:
            return True
        now = self._now()
        window_start = now - 60.0
        hits = [t for t in self._hits[key] if t > window_start]
        if len(hits) >= self.per_minute:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True

    def reset(self) -> None:
        self._hits.clear()


def client_ip(request) -> str:
    """Best-effort client IP. Fly.io sets X-Forwarded-For; take the first
    (outermost) entry, fall back to the direct peer address."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = getattr(request, "client", None)
    return client.host if client else "unknown"
