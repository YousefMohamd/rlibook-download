"""Rate limiter tests (fake clock, no network)."""
from __future__ import annotations

from app.ratelimit import RateLimiter


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_limit():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=3, now_fn=clock)
    assert limiter.allow("1.2.3.4")
    assert limiter.allow("1.2.3.4")
    assert limiter.allow("1.2.3.4")
    assert not limiter.allow("1.2.3.4")


def test_limits_are_per_key():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=1, now_fn=clock)
    assert limiter.allow("1.1.1.1")
    assert limiter.allow("2.2.2.2")
    assert not limiter.allow("1.1.1.1")


def test_window_slides():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=2, now_fn=clock)
    assert limiter.allow("ip")
    assert limiter.allow("ip")
    assert not limiter.allow("ip")
    clock.now += 61  # past the 60 s window
    assert limiter.allow("ip")


def test_disabled_when_zero():
    limiter = RateLimiter(per_minute=0)
    for _ in range(100):
        assert limiter.allow("ip")


def test_client_ip_prefers_forwarded_for():
    from app.ratelimit import client_ip

    class Req:
        headers = {"x-forwarded-for": "203.0.113.9, 10.0.0.1"}
        client = type("C", (), {"host": "10.0.0.2"})()

    assert client_ip(Req()) == "203.0.113.9"


def test_client_ip_falls_back_to_peer():
    from app.ratelimit import client_ip

    class Req:
        headers = {}
        client = type("C", (), {"host": "10.0.0.2"})()

    assert client_ip(Req()) == "10.0.0.2"
