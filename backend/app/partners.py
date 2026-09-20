from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger("champ.partners")


class RateLimiter:
    def __init__(self, per_minute: int, per_second: int, concurrency: int) -> None:
        self.per_minute = per_minute
        self.per_second = per_second
        self.sem = asyncio.Semaphore(concurrency)
        self._minute: list[float] = []
        self._second: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                self._minute = [t for t in self._minute if now - t < 60]
                self._second = [t for t in self._second if now - t < 1]
                if (
                    len(self._minute) < self.per_minute
                    and len(self._second) < self.per_second
                ):
                    self._minute.append(now)
                    self._second.append(now)
                    break
                wait_m = 60 - (now - self._minute[0]) if self._minute else 0
                wait_s = 1 - (now - self._second[0]) if self._second else 0
                wait = max(wait_m, wait_s, 0.05)
            await asyncio.sleep(wait)
        await self.sem.acquire()

    def release(self) -> None:
        self.sem.release()


class PartnersClient:
    def __init__(self) -> None:
        self.base = settings.partners_base_url.rstrip("/")
        self.token = settings.partners_token
        self.partner_id = settings.partners_id
        self._stats = RateLimiter(10, 2, 1)
        self._info = RateLimiter(30, 3, 3)
        self._http = httpx.AsyncClient(timeout=30.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def _get(self, limiter: RateLimiter, url: str, params: dict | None = None) -> Any:
        await limiter.acquire()
        try:
            for attempt in range(5):
                resp = await self._http.get(url, headers=self._headers(), params=params)
                if resp.status_code == 429:
                    retry = resp.headers.get("Retry-After")
                    wait = float(retry) if retry else 2 + attempt
                    log.warning("429 from %s, sleep %s", url, wait)
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp.json()
            raise RuntimeError(f"rate-limited: {url}")
        finally:
            limiter.release()

    async def statistics_traders(self, day: str) -> dict:
        params = {
            "dateFrom": day,
            "dateThrough": day,
            "group1": "trader",
            "deposited": "1",
            "fields": "depo_sum,wdrw_sum,net_dep,count_depo,count_ftd,ftd_sum,count_trades",
            "sort_by": "depo_sum",
            "sort_direction": "desc",
        }
        url = f"{self.base}/api/v1/statistics"
        data = await self._get(self._stats, url, params)
        return data or {}

    async def user_info(self, uid: int) -> dict | None:
        url = f"{self.base}/api/v1/user-info/{uid}/{self.partner_id}"
        return await self._get(self._info, url)


partners_client = PartnersClient()
