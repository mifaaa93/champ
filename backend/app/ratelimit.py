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


def ip_from_headers(x_real: str, forwarded: str, fallback: str = "") -> str:
    real = (x_real or "").strip()
    if real:
        return real[:64]
    parts = [part.strip() for part in (forwarded or "").split(",") if part.strip()]
    if parts:
        return parts[-1][:64]
    return (fallback or "unknown")[:64]


def client_ip(request: Request) -> str:
    fallback = request.client.host if request.client and request.client.host else ""
    return ip_from_headers(
        request.headers.get("x-real-ip", ""),
        request.headers.get("x-forwarded-for", ""),
        fallback,
    )
