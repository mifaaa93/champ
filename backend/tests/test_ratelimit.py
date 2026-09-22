import asyncio

from app.ratelimit import SlidingWindow


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
