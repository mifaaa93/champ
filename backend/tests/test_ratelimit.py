import asyncio

from app.ratelimit import SlidingWindow, client_ip, ip_from_headers
from types import SimpleNamespace


def test_window_blocks_after_limit():
    box = SlidingWindow()

    async def run():
        ok1, _ = await box.allow("ip", 2, 60)
        ok2, _ = await box.allow("ip", 2, 60)
        ok3, retry = await box.allow("ip", 2, 60)
        return ok1, ok2, ok3, retry

    a, b, c, retry = asyncio.run(run())
    assert a and b
    assert not c
    assert retry >= 1


def test_client_ip_prefers_real_and_ignores_spoofed_prefix():
    assert ip_from_headers("203.0.113.9", "1.1.1.1, 203.0.113.9", "10.0.0.1") == "203.0.113.9"
    assert ip_from_headers("", "1.1.1.1, 203.0.113.9", "10.0.0.1") == "203.0.113.9"
    assert ip_from_headers("", "", "10.0.0.1") == "10.0.0.1"


def test_direct_api_cannot_spoof_rate_limit_ip():
    request = SimpleNamespace(
        client=SimpleNamespace(host="203.0.113.42"),
        headers={"x-real-ip": "1.1.1.1", "x-forwarded-for": "2.2.2.2"},
    )
    assert client_ip(request) == "203.0.113.42"
