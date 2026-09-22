from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.db import SessionLocal
from app.models import DayResult, PublishLog
from app.ledger import money
from app.services.freeze import freeze_day, load_rank_rows
from app.services.poll import refresh_statistics, snapshot_watchlist
from app.services.ranking import eligible_only, pick_winners, sort_loss, sort_yield
from app.settings_service import get_settings, job_get, job_set
from app.telegram import (
    TelegramHtmlError,
    build_final_message,
    build_hourly_message,
    send_message,
)
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


def _pack(seq, *, loss: bool = False):
    return [
        {
            "uid": r.uid,
            "nickname": r.nickname,
            "return_pct": float(r.trading_return_pct if loss else r.return_pct),
            "pnl": float(r.trading_pnl if loss else r.contest_pnl),
        }
        for r in seq
    ]


async def telegram_board(session, day=None) -> dict:
    from app.config import settings as app_settings

    cfg = await get_settings(session)
    now = now_dubai()
    day = day or dubai_today()
    rows = eligible_only(await load_rank_rows(session, day))
    top_n = int(cfg["top_n"])
    min_pct = float(cfg.get("min_return_pct") or 0)
    y_all = sort_yield(rows)
    if min_pct > 0:
        y_all = [r for r in y_all if float(r.return_pct) >= min_pct]
    y = y_all[:top_n]
    loss = [r for r in sort_loss(rows) if r.trading_pnl < 0][:top_n]
    winners = {"yield": [], "loss": []}
    frozen = list(
        (await session.execute(select(DayResult).where(DayResult.day == day))).scalars()
    )
    if frozen:
        for it in frozen:
            winners.setdefault(it.nomination, []).append(
                {
                    "place": it.place,
                    "uid": it.uid,
                    "nickname": "",
                    "return_pct": float(it.metric) if it.nomination == "yield" else 0,
                    "pnl": float(it.pnl),
                    "prize_amount": float(it.prize_amount),
                }
            )
        source = "frozen"
    else:
        source = "draft"
        picked = pick_winners(
            await load_rank_rows(session, day),
            int(cfg["prize_places"]),
            list(cfg["prize_yield"]),
            list(cfg["prize_loss_pct"]),
            money(cfg["loss_comp_cap"]),
        )
        for nom, items in picked.items():
            winners[nom] = [
                {
                    "place": item["place"],
                    "uid": item["uid"],
                    "nickname": item.get("nickname") or "",
                    "return_pct": float(item.get("metric") or 0),
                    "pnl": float(item["pnl"]),
                    "prize_amount": float(item["prize_amount"]),
                }
                for item in items
            ]
    site = app_settings.site_public_url or ""
    return {
        "day": str(day),
        "time": now.strftime("%H:%M"),
        "site": site,
        "hourly_yield": _pack(y),
        "hourly_loss": _pack(loss, loss=True),
        "final_source": source,
        "final_yield": winners.get("yield") or [],
        "final_loss": winners.get("loss") or [],
    }


async def compose_hourly(session, day=None) -> str:
    cfg = await get_settings(session)
    now = now_dubai()
    day = day or dubai_today()
    rows = eligible_only(await load_rank_rows(session, day))
    top_n = int(cfg["top_n"])
    min_pct = float(cfg.get("min_return_pct") or 0)
    y_all = sort_yield(rows)
    if min_pct > 0:
        y_all = [r for r in y_all if float(r.return_pct) >= min_pct]
    y = y_all[:top_n]
    loss = [r for r in sort_loss(rows) if r.trading_pnl < 0][:top_n]
    return build_hourly_message(
        str(day), now.strftime("%H:%M"), _pack(y), _pack(loss, loss=True), cfg
    )


async def compose_final(session, day=None) -> tuple[str, str]:
    cfg = await get_settings(session)
    day = day or dubai_today()
    frozen = list(
        (await session.execute(select(DayResult).where(DayResult.day == day))).scalars()
    )
    winners: dict[str, list] = {"yield": [], "loss": []}
    source = "frozen"
    if frozen:
        for it in frozen:
            winners.setdefault(it.nomination, []).append(
                {
                    "place": it.place,
                    "uid": it.uid,
                    "prize_amount": it.prize_amount,
                }
            )
    else:
        source = "draft"
        picked = pick_winners(
            await load_rank_rows(session, day),
            int(cfg["prize_places"]),
            list(cfg["prize_yield"]),
            list(cfg["prize_loss_pct"]),
            money(cfg["loss_comp_cap"]),
        )
        for nom, items in picked.items():
            winners[nom] = [
                {
                    "place": item["place"],
                    "uid": item["uid"],
                    "prize_amount": item["prize_amount"],
                }
                for item in items
            ]
    return build_final_message(str(day), winners, cfg), source


async def job_publish(kind: str = "hourly", day=None, force: bool = False) -> None:
    async with SessionLocal() as session:
        cfg = await get_settings(session)
        now = now_dubai()
        day = day or dubai_today()
        state = await job_get(session, "publish")
        if kind == "hourly" and now.hour == 0:
            return
        if kind == "hourly" and not force:
            interval_m = int(cfg.get("publish_interval_minutes") or 60)
            last = state.get("last_publish_ts")
            if not last:
                state["last_publish_ts"] = now.isoformat()
                await job_set(session, "publish", state)
                return
            if last:
                try:
                    last_dt = datetime.fromisoformat(last)
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=now.tzinfo)
                    elapsed = (now - last_dt.astimezone(now.tzinfo)).total_seconds()
                    if elapsed < interval_m * 60:
                        return
                except ValueError:
                    pass
        if kind == "final" and not force and state.get("last_final") == str(day):
            return

        if kind == "final":
            text, _source = await compose_final(session, day)
        else:
            text = await compose_hourly(session, day)

        try:
            sent = await send_message(text)
        except TelegramHtmlError as exc:
            log.error("telegram html invalid: %s", exc.errors)
            if force:
                raise
            sent = False
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
            state["last_publish_ts"] = now.isoformat()
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
    scheduler = AsyncIOScheduler(timezone="Africa/Johannesburg")
    scheduler.add_job(job_statistics, "interval", minutes=10, id="stats", max_instances=1)
    scheduler.add_job(job_snapshots, "interval", minutes=5, id="snaps", max_instances=1)
    scheduler.add_job(job_publish, "interval", minutes=1, id="hourly", max_instances=1)
    scheduler.add_job(
        job_freeze_and_rollover, "interval", seconds=30, id="freeze", max_instances=1
    )
    return scheduler
