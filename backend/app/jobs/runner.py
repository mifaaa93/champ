from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.db import SessionLocal
from app.models import DayLedger, DayResult, Participant, PublishLog
from app.ledger import money, return_pct
from app.services.freeze import freeze_day, load_rank_rows
from app.services.poll import refresh_statistics, snapshot_watchlist
from app.services.ranking import loss_pool, pick_winners, yield_pool
from app.settings_service import get_settings, job_get, job_set
from app.telegram import (
    TelegramHtmlError,
    TelegramSendError,
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
        from app.services.event import refresh_season_statistics

        try:
            season = await refresh_season_statistics(session)
            log.info("season stats %s", season)
        except Exception:
            log.exception("season stats failed")


async def job_snapshots() -> None:
    async with SessionLocal() as session:
        result = await snapshot_watchlist(session)
        log.info("snapshots %s", result)
        from app.services.event import refresh_event_board

        await refresh_event_board(session)


async def job_dummy_tick() -> None:
    async with SessionLocal() as session:
        from app.services.event import refresh_event_board, tick_showcase
        from app.timezone import now_champ

        cfg = await get_settings(session)
        interval_m = float(cfg.get("dummy_tick_minutes") or 1)
        interval_m = max(0.5, min(interval_m, 1440))
        state = await job_get(session, "dummy_tick")
        now = now_champ()
        last = state.get("last_ts")
        if last:
            try:
                last_dt = datetime.fromisoformat(str(last))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=now.tzinfo)
                if (now - last_dt.astimezone(now.tzinfo)).total_seconds() < interval_m * 60:
                    return
            except ValueError:
                pass
        changed = await tick_showcase(session)
        await refresh_event_board(session)
        await job_set(session, "dummy_tick", {"last_ts": now.isoformat()})
        log.info("dummy tick changed=%s", changed)


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
    rows = await load_rank_rows(session, day)
    top_n = int(cfg["top_n"])
    min_pct = float(cfg.get("min_return_pct") or 0)
    y_all = yield_pool(rows)
    if min_pct > 0:
        y_all = [r for r in y_all if float(r.return_pct) >= min_pct]
    y = y_all[:top_n]
    loss = loss_pool(rows)[:top_n]
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
                    "metric": it.metric,
                    "pnl": it.pnl,
                    "prize_amount": it.prize_amount,
                    "card": it.card or {},
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
            winners[nom] = list(items)
    winners = await _hydrate_winners(session, day, winners)
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


async def _hydrate_winners(session, day, winners: dict) -> dict:
    uids = [int(it["uid"]) for items in winners.values() for it in items]
    parts: dict = {}
    leds: dict = {}
    if uids:
        parts = {
            p.uid: p
            for p in (
                await session.execute(select(Participant).where(Participant.uid.in_(uids)))
            ).scalars()
        }
        leds = {
            led.uid: led
            for led in (
                await session.execute(
                    select(DayLedger).where(DayLedger.day == day, DayLedger.uid.in_(uids))
                )
            ).scalars()
        }
    out: dict[str, list] = {}
    for nom, items in winners.items():
        packed = []
        for it in items:
            uid = int(it["uid"])
            card = it.get("card") or {}
            part = parts.get(uid)
            led = leds.get(uid)
            nick = card.get("nickname") or it.get("nickname") or (part.nickname if part else "") or ""
            if nom == "loss":
                pct = card.get("trading_return_pct")
                if pct is None and led is not None:
                    pct = float(return_pct(led.trading_pnl, led.basis))
                pnl = it.get("pnl")
                if pnl is None and led is not None:
                    pnl = led.trading_pnl
            else:
                pct = card.get("return_pct")
                if pct is None:
                    pct = it.get("return_pct", it.get("metric"))
                if pct is None and led is not None:
                    pct = led.return_pct
                pnl = it.get("pnl")
                if pnl is None and led is not None:
                    pnl = led.contest_pnl
            packed.append(
                {
                    "place": it["place"],
                    "uid": uid,
                    "nickname": nick,
                    "return_pct": float(pct or 0),
                    "pnl": float(pnl or 0),
                    "prize_amount": float(it.get("prize_amount") or 0),
                }
            )
        out[nom] = packed
    return out


async def compose_hourly(session, day=None) -> str:
    cfg = await get_settings(session)
    now = now_dubai()
    day = day or dubai_today()
    rows = await load_rank_rows(session, day)
    top_n = int(cfg["top_n"])
    min_pct = float(cfg.get("min_return_pct") or 0)
    y_all = yield_pool(rows)
    if min_pct > 0:
        y_all = [r for r in y_all if float(r.return_pct) >= min_pct]
    y = y_all[:top_n]
    loss = loss_pool(rows)[:top_n]
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
                    "pnl": it.pnl,
                    "metric": it.metric,
                    "card": it.card or {},
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
                    "nickname": item.get("nickname") or "",
                    "metric": item.get("metric"),
                    "pnl": item.get("pnl"),
                    "prize_amount": item["prize_amount"],
                }
                for item in items
            ]
    winners = await _hydrate_winners(session, day, winners)
    return build_final_message(str(day), winners, cfg), source


async def job_publish(kind: str = "hourly", day=None, force: bool = False) -> dict:
    async with SessionLocal() as session:
        cfg = await get_settings(session)
        now = now_dubai()
        day = day or dubai_today()
        state = await job_get(session, "publish")
        if kind == "hourly" and now.hour == 0 and not force:
            return {"status": "skipped", "reason": "midnight"}
        if kind == "hourly" and not force:
            interval_m = int(cfg.get("publish_interval_minutes") or 60)
            last = state.get("last_publish_ts")
            if not last:
                state["last_publish_ts"] = now.isoformat()
                await job_set(session, "publish", state)
                return {"status": "skipped", "reason": "seed"}
            if last:
                try:
                    last_dt = datetime.fromisoformat(last)
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=now.tzinfo)
                    elapsed = (now - last_dt.astimezone(now.tzinfo)).total_seconds()
                    if elapsed < interval_m * 60:
                        return {"status": "skipped", "reason": "interval"}
                except ValueError:
                    pass
        if kind == "final" and not force and state.get("last_final") == str(day):
            return {"status": "skipped", "reason": "already"}

        if kind == "final":
            text, _source = await compose_final(session, day)
        else:
            text = await compose_hourly(session, day)

        try:
            sent = await send_message(
                text,
                token=str(cfg.get("tg_bot_token") or ""),
                chat_id=str(cfg.get("tg_chat_id") or ""),
            )
        except TelegramHtmlError as exc:
            log.error("telegram html invalid: %s", exc.errors)
            if force:
                raise
            sent = False
        if not sent:
            state["last_fail"] = {"kind": kind, "day": str(day), "at": now.isoformat()}
            await job_set(session, "publish", state)
            log.error("publish %s failed", kind)
            if force:
                raise TelegramSendError("Telegram не отправлен. Проверь токен бота и ID группы.")
            return {"status": "failed", "sent": False}
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
        return {"status": "sent", "sent": True}


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
            marker = await job_get(session, "day_closed")
            closed_empty = day.isoformat() in {str(item) for item in (marker.get("days") or [])}
            if existing or closed_empty:
                await job_publish("final", day=day)


async def recover() -> None:
    async with SessionLocal() as session:
        today = dubai_today()
        days = (
            await session.execute(
                select(DayLedger.day).where(DayLedger.day < today).distinct()
            )
        ).scalars().all()
        closed = set(
            (
                await session.execute(
                    select(DayResult.day).where(DayResult.day < today).distinct()
                )
            ).scalars().all()
        )
        marker = await job_get(session, "day_closed")
        marked = {str(item) for item in (marker.get("days") or [])}
        pending = sorted(
            day for day in set(days) if day not in closed and day.isoformat() not in marked
        )
        for day in pending:
            log.info("recover freeze for %s", day)
            result = await freeze_day(session, day)
            if int(result.get("count") or 0) == 0:
                marked.add(day.isoformat())
                await job_set(session, "day_closed", {"days": sorted(marked)})


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Africa/Johannesburg")
    scheduler.add_job(job_statistics, "interval", minutes=10, id="stats", max_instances=1)
    scheduler.add_job(job_snapshots, "interval", minutes=5, id="snaps", max_instances=1)
    scheduler.add_job(job_dummy_tick, "interval", seconds=30, id="dummies", max_instances=1)
    scheduler.add_job(job_publish, "interval", minutes=1, id="hourly", max_instances=1)
    scheduler.add_job(
        job_freeze_and_rollover, "interval", seconds=30, id="freeze", max_instances=1
    )
    return scheduler
