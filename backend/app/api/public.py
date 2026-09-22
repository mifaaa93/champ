from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import DayLedger, DayResult, Participant, Snapshot, Trader
from app.ratelimit import client_ip, limiter
from app.schemas import RegisterIn, day_cash, dec, row_out
from app.services.freeze import load_rank_rows
from app.services.ranking import eligible_only, sort_loss, sort_yield
from app.services.register import register_participant
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


@router.get("/leaderboard")
async def leaderboard(
    nomination: str = Query("yield", pattern="^(yield|loss)$"),
    day: date | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    cfg = await get_settings(session)
    day = day or dubai_today()
    rows = await load_rank_rows(session, day)
    live = eligible_only(rows)
    ordered = sort_yield(live) if nomination == "yield" else sort_loss(live)
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
