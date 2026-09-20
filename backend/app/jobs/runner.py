from __future__ import annotations

import logging
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.db import SessionLocal
from app.models import DayResult, PublishLog
from app.services.freeze import freeze_day, load_rank_rows
from app.services.poll import refresh_statistics, snapshot_watchlist
from app.services.ranking import eligible_only, sort_loss, sort_yield
from app.settings_service import get_settings, job_get, job_set
from app.telegram import build_final_message, build_hourly_message, send_message
from app.timezone import dubai_today, is_final_post_window, is_freeze_window, now_dubai

log = logging.getLogger("champ.jobs")


async def job_statistics() -> None:
    async with SessionLocal() as session:
        result = await refresh_statistics(session)
        log.info("statistics %s", result)


async def job_snapshots() -> None:
    async with SessionLocal() as session:
        result = await snapshot_watchlist(session)
        log.info("snapshots %s", result)


async def job_publish(kind: str = "hourly", day=None) -> None:
    async with SessionLocal() as session:
        cfg = await get_settings(session)
        now = now_dubai()
        day = day or dubai_today()
        state = await job_get(session, "publish")
        stamp = f"{day.isoformat()}T{now.hour:02d}"
        if kind == "hourly" and now.hour == 0:
            return
        if kind == "hourly" and state.get("last_hour") == stamp:
            return
        if kind == "final" and state.get("last_final") == str(day):
            return

        rows = eligible_only(await load_rank_rows(session, day))
        top_n = int(cfg["top_n"])
        y = sort_yield(rows)[:top_n]
        loss = [r for r in sort_loss(rows) if r.contest_pnl < 0][:top_n]

        def pack(seq):
            return [
                {
                    "uid": r.uid,
                    "nickname": r.nickname,
                    "return_pct": float(r.return_pct),
                    "pnl": float(r.contest_pnl),
                }
                for r in seq
            ]

        if kind == "final":
            winners = {"yield": [], "loss": []}
            q = await session.execute(select(DayResult).where(DayResult.day == day))
            for it in q.scalars():
                winners.setdefault(it.nomination, []).append(
                    {
                        "place": it.place,
                        "uid": it.uid,
                        "prize_amount": it.prize_amount,
                    }
                )
            text = build_final_message(str(day), winners)
        else:
            text = build_hourly_message(
                str(day), now.strftime("%H:%M"), pack(y), pack(loss)
            )

        sent = await send_message(text)
        session.add(
            PublishLog(
                channel="telegram",
                day=day,
                kind=kind,
                payload=text,
            )
        )
        if kind == "final":
            state["last_final"] = str(day)
        else:
            state["last_hour"] = stamp
        await job_set(session, "publish", state)
        log.info("publish %s sent=%s", kind, sent)


async def job_freeze_and_rollover() -> None:
    async with SessionLocal() as session:
        now = now_dubai()
        if is_freeze_window(now):
            result = await freeze_day(session, now.date())
            log.info("freeze %s", result)
        if is_final_post_window(now):
            day = now.date() - timedelta(days=1)
            existing = (
                await session.execute(select(DayResult).where(DayResult.day == day))
            ).scalars().first()
            if existing:
                await job_publish("final", day=day)


async def recover() -> None:
    async with SessionLocal() as session:
        today = dubai_today()
        yesterday = today - timedelta(days=1)
        y_has = (
            await session.execute(select(DayResult).where(DayResult.day == yesterday))
        ).scalars().first()
        if not y_has:
            from app.models import DayLedger

            led = (
                await session.execute(select(DayLedger).where(DayLedger.day == yesterday))
            ).scalars().first()
            if led:
                log.info("recover freeze for %s", yesterday)
                await freeze_day(session, yesterday)


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Dubai")
    scheduler.add_job(job_statistics, "interval", minutes=10, id="stats", max_instances=1)
    scheduler.add_job(job_snapshots, "interval", minutes=5, id="snaps", max_instances=1)
    scheduler.add_job(job_publish, "cron", minute=0, id="hourly", max_instances=1)
    scheduler.add_job(
        job_freeze_and_rollover, "interval", seconds=30, id="freeze", max_instances=1
    )
    return scheduler
