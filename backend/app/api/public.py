from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import DayLedger, DayResult, Participant, Snapshot, Trader
from app.ratelimit import client_ip, limiter

from app.services.freeze import load_rank_rows
from app.ledger import money as to_money
from app.services.ranking import loss_pool, loss_target, yield_pool, yield_target
from app.services.event import invite_preview, lookup_event_uid, public_event, register_event_name
from app.services.register import register_participant
from app.schemas import EventRegisterIn, RegisterIn, day_cash, dec, row_out
from app.settings_service import get_settings
from app.timezone import (
    TZ_LABEL,
    champ_day_end,
    dubai_today,
    now_dubai,
    seconds_until_dubai_midnight,
)

router = APIRouter(prefix="/public")


@router.get("/meta")
async def meta(session: AsyncSession = Depends(get_session)) -> dict:
    cfg = await get_settings(session)
    now = now_dubai()
    day = dubai_today()
    return {
        "timezone": TZ_LABEL,
        "now": now.isoformat(),
        "day": str(day),
        "day_end": champ_day_end(day).isoformat(),
        "seconds_to_close": seconds_until_dubai_midnight(now),
        "top_n": cfg["top_n"],
        "min_day_deposit": cfg["min_day_deposit"],
        "prize_yield": cfg["prize_yield"],
        "prize_loss_pct": cfg["prize_loss_pct"],
        "loss_comp_cap": cfg["loss_comp_cap"],
        "prize_places": cfg["prize_places"],
    }


@router.get("/event")
async def event_page(session: AsyncSession = Depends(get_session)) -> dict:
    return await public_event(session)


@router.get("/event/lookup/{uid}")
async def event_lookup(
    uid: int, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    ip = client_ip(request)
    ok, retry = await limiter.allow(f"elook:{ip}", 20, 60)
    if not ok:
        raise HTTPException(429, f"Слишком часто. Подождите {retry} с.")
    return await lookup_event_uid(session, uid)


@router.post("/event/register")
async def event_register(
    body: EventRegisterIn, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    ip = client_ip(request)
    burst_ok, burst_retry = await limiter.allow(f"ereg:burst:{ip}", 2, 20)
    if not burst_ok:
        raise HTTPException(429, f"Слишком часто. Подождите {burst_retry} с.")
    hour_ok, hour_retry = await limiter.allow(f"ereg:hour:{ip}", 5, 3600)
    if not hour_ok:
        raise HTTPException(
            429,
            f"Лимит регистраций с этого адреса. Попробуйте через {max(1, hour_retry // 60)} мин.",
        )
    if body.website.strip():
        return {
            "uid": body.uid,
            "status": "ok",
            "you": {
                "uid": body.uid,
                "name": body.nickname,
                "rank": 80,
                "dep": 0,
                "turn": 0,
                "beaten": 0,
                "total": 1,
                "neighbors": [],
            },
        }
    return await register_event_name(session, body.uid, body.nickname, body.telegram)


@router.get("/event/invite/{uid}")
async def event_invite(uid: int, session: AsyncSession = Depends(get_session)) -> dict:
    return await invite_preview(session, uid)


@router.post("/register")
async def register(
    body: RegisterIn, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    ip = client_ip(request)
    burst_ok, burst_retry = await limiter.allow(f"reg:burst:{ip}", 2, 20)
    if not burst_ok:
        raise HTTPException(
            status_code=429,
            detail=f"Слишком часто. Подождите {burst_retry} с.",
        )
    hour_ok, hour_retry = await limiter.allow(f"reg:hour:{ip}", 5, 3600)
    if not hour_ok:
        raise HTTPException(
            status_code=429,
            detail=f"Лимит регистраций с этого адреса. Попробуйте через {max(1, hour_retry // 60)} мин.",
        )
    if body.website.strip():
        return {
            "ok": True,
            "uid": body.uid,
            "nickname": body.nickname,
            "message": "Регистрация принята.",
        }

    cfg = await get_settings(session)
    min_dep = cfg["min_day_deposit"]
    part = await register_participant(session, body.uid, body.nickname, body.telegram)
    from app.services.poll import refresh_statistics, snapshot_uid

    try:
        await snapshot_uid(session, part.uid)
        await refresh_statistics(session)
    except Exception:
        pass
    return {
        "ok": True,
        "uid": part.uid,
        "nickname": part.nickname,
        "message": (
            f"Регистрация принята. Депозит от ${min_dep:g} за сегодняшние сутки {TZ_LABEL} "
            "попадёт в рейтинг."
        ),
    }


@router.get("/lookup/{uid}")
async def lookup(uid: int, request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    ip = client_ip(request)
    ok, retry = await limiter.allow(f"lookup:{ip}", 20, 60)
    if not ok:
        raise HTTPException(429, f"Слишком часто. Подождите {retry} с.")
    if uid < 100_000 or uid > 9_999_999_999:
        raise HTTPException(400, "Некорректный UID")

    cfg = await get_settings(session)
    day = dubai_today()
    rows = await load_rank_rows(session, day)
    y_pool = yield_pool(rows)
    min_pct = float(cfg.get("min_return_pct") or 0)
    if min_pct > 0:
        y_pool = [r for r in y_pool if float(r.return_pct) >= min_pct]
    l_pool = loss_pool(rows)
    top_n = int(cfg["top_n"])
    prizes = int(cfg["prize_places"])

    part = (
        await session.execute(select(Participant).where(Participant.uid == uid))
    ).scalar_one_or_none()
    me = next((r for r in rows if r.uid == uid), None)

    min_dep_d = to_money(cfg["min_day_deposit"])
    deposited = 0.0
    if me:
        deposited = float(max(me.day_deposits, 0))
    need_deposit = max(0.0, float(min_dep_d) - deposited)

    y_place = next((i for i, r in enumerate(y_pool, 1) if r.uid == uid), None)
    l_place = next((i for i, r in enumerate(l_pool, 1) if r.uid == uid), None)

    reasons = (me.dq_reason.split(",") if me and me.dq_reason else []) if me and not me.eligible else []
    if not part:
        status = "not_registered"
    elif not me or not me.eligible:
        status = "not_in_day"
        if me:
            reasons = [x for x in (me.dq_reason or "").split(",") if x]
        else:
            reasons = ["no_start"]
    elif y_place is None and l_place is None:
        status = "not_in_lists"
    else:
        status = "ranked"

    snapshot = None
    if me:
        snapshot = {
            "nickname": me.nickname,
            "eligible": me.eligible,
            "dq_reason": me.dq_reason,
            "balance": dec(me.last_balance),
            "pnl": dec(me.contest_pnl),
            "trading_pnl": dec(me.trading_pnl),
            "return_pct": dec(me.return_pct),
            "deposits": dec(me.day_deposits),
            "withdrawals": dec(me.day_withdrawals),
            "basis": dec(me.basis),
        }

    return {
        "uid": uid,
        "day": str(day),
        "status": status,
        "registered": part is not None,
        "reasons": reasons,
        "need_deposit": need_deposit,
        "min_day_deposit": float(min_dep_d),
        "require_trade": bool(cfg["require_trade"]),
        "top_n": top_n,
        "prize_places": prizes,
        "min_return_pct": min_pct,
        "yield": {
            "place": y_place,
            "count": len(y_pool),
            "top_n": yield_target(me, y_pool, top_n),
            "prize": yield_target(me, y_pool, prizes),
            "first": yield_target(me, y_pool, 1),
        },
        "loss": {
            "place": l_place,
            "count": len(l_pool),
            "top_n": loss_target(me, l_pool, top_n),
            "prize": loss_target(me, l_pool, prizes),
            "first": loss_target(me, l_pool, 1),
        },
        "you": snapshot,
    }


@router.get("/leaderboard")
async def leaderboard(
    nomination: str = Query("yield", pattern="^(yield|loss)$"),
    day: date | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    cfg = await get_settings(session)
    day = day or dubai_today()
    rows = await load_rank_rows(session, day)
    ordered = yield_pool(rows) if nomination == "yield" else loss_pool(rows)
    top = ordered[: int(cfg["top_n"])]
    out = []
    for i, r in enumerate(top, 1):
        item = {
            "place": i,
            "uid": r.uid,
            "nickname": r.nickname,
            "balance": dec(r.last_balance),
            "pnl": dec(r.trading_pnl if nomination == "loss" else r.contest_pnl),
            "return_pct": dec(
                r.trading_return_pct if nomination == "loss" else r.return_pct
            ),
            "deposits": dec(r.day_deposits),
            "withdrawals": dec(r.day_withdrawals),
            "bonuses": dec(r.day_bonuses),
            "eligible": r.eligible,
        }
        out.append(item)
    return {"day": str(day), "nomination": nomination, "top_n": cfg["top_n"], "rows": out}


@router.get("/trader/{uid}")
async def trader(uid: int, session: AsyncSession = Depends(get_session)) -> dict:
    day = dubai_today()
    part = (
        await session.execute(select(Participant).where(Participant.uid == uid))
    ).scalar_one_or_none()
    led = (
        await session.execute(
            select(DayLedger).where(DayLedger.day == day, DayLedger.uid == uid)
        )
    ).scalar_one_or_none()
    if not part and not led:
        raise HTTPException(404, "not found")
    snap = None
    start = None
    if led and led.last_snapshot_id:
        snap = await session.get(Snapshot, led.last_snapshot_id)
    if led and led.start_snapshot_id:
        start = await session.get(Snapshot, led.start_snapshot_id)
    ledger = (
        row_out(
            led,
            snap.ts if snap else None,
            start.ts if start else None,
        )
        if led
        else None
    )
    if ledger is not None:
        ledger["trades"] = int(led.stats_trades or 0)
        ledger["status"] = led.status or ""
        ledger["self_excluded"] = bool(led.self_excluded)
    trader = await session.get(Trader, uid)
    country = (part.country if part else "") or (trader.country if trader else "") or ""
    return {
        "uid": uid,
        "nickname": part.nickname if part else "",
        "telegram": part.telegram if part else "",
        "country": country,
        "registered": part is not None,
        "registered_at": part.created_at.isoformat() if part and part.created_at else None,
        "last_checked_at": snap.ts.isoformat() if snap else (
            led.updated_at.isoformat() if led and led.updated_at else None
        ),
        "day": str(day),
        "ledger": ledger,
    }


@router.get("/archive")
async def archive(session: AsyncSession = Depends(get_session)) -> dict:
    q = await session.execute(select(DayResult.day).distinct().order_by(DayResult.day.desc()))
    days = [str(d) for d in q.scalars()]
    return {"days": days}


@router.get("/archive/{day}")
async def archive_day(day: date, session: AsyncSession = Depends(get_session)) -> dict:
    q = await session.execute(
        select(DayResult).where(DayResult.day == day).order_by(DayResult.nomination, DayResult.place)
    )
    items = q.scalars().all()
    if not items:
        raise HTTPException(404, "day not frozen")
    uids = [it.uid for it in items]
    parts = {
        p.uid: p
        for p in (
            await session.execute(select(Participant).where(Participant.uid.in_(uids)))
        ).scalars()
    }
    ledgers = {
        led.uid: led
        for led in (
            await session.execute(
                select(DayLedger).where(DayLedger.day == day, DayLedger.uid.in_(uids))
            )
        ).scalars()
    }
    grouped = {"yield": [], "loss": []}
    frozen_at = items[0].frozen_at.isoformat() if items[0].frozen_at else None
    for it in items:
        part = parts.get(it.uid)
        led = ledgers.get(it.uid)
        grouped.setdefault(it.nomination, []).append(
            {
                "place": it.place,
                "uid": it.uid,
                "nickname": part.nickname if part else "",
                "telegram": part.telegram if part else "",
                "country": (part.country if part else "") or "",
                "metric": dec(it.metric),
                "pnl": dec(it.pnl),
                "prize_amount": dec(it.prize_amount),
                "prize_note": it.prize_note,
                "balance": dec(led.last_balance) if led else None,
                "start_balance": dec(led.start_balance) if led else None,
                "deposits": dec(day_cash(led.day_deposits, led.stats_depo_sum)) if led else None,
                "withdrawals": dec(day_cash(led.day_withdrawals, led.stats_wdrw_sum)) if led else None,
                "bonuses": dec(led.day_bonuses) if led else None,
                "return_pct": dec(led.return_pct) if led else None,
                "trading_pnl": dec(led.trading_pnl) if led else None,
                "trades": int(led.stats_trades) if led else None,
            }
        )
    return {"day": str(day), "frozen": True, "frozen_at": frozen_at, "winners": grouped}
