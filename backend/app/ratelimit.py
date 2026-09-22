from __future__ import annotations

import asyncio
import time

from fastapi import Request


class SlidingWindow:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def allow(self, key: str, limit: int, window_s: float) -> tuple[bool, int]:
        now = time.monotonic()
        async with self._lock:
            q = [t for t in self._hits.get(key, []) if now - t < window_s]
            if len(q) >= limit:
                self._hits[key] = q
                retry = max(1, int(window_s - (now - q[0])) + 1)
                return False, retry
            q.append(now)
            self._hits[key] = q
            return True, 0


limiter = SlidingWindow()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    real = request.headers.get("x-real-ip", "").strip()
    if real:
        return real[:64]
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
