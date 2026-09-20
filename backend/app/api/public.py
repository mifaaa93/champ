from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import DayLedger, DayResult, Participant, Snapshot
from app.schemas import RegisterIn, dec, row_out
from app.services.freeze import load_rank_rows
from app.services.ranking import eligible_only, sort_loss, sort_yield
from app.services.register import register_participant
from app.settings_service import get_settings
from app.timezone import dubai_today, now_dubai, seconds_until_dubai_midnight

router = APIRouter(prefix="/public")


@router.get("/meta")
async def meta(session: AsyncSession = Depends(get_session)) -> dict:
    cfg = await get_settings(session)
    now = now_dubai()
    day = dubai_today()
    return {
        "timezone": "Asia/Dubai",
        "now": now.isoformat(),
        "day": str(day),
        "seconds_to_close": seconds_until_dubai_midnight(now),
        "top_n": cfg["top_n"],
        "min_day_deposit": cfg["min_day_deposit"],
        "prize_yield": cfg["prize_yield"],
        "prize_loss_pct": cfg["prize_loss_pct"],
        "loss_comp_cap": cfg["loss_comp_cap"],
        "prize_places": cfg["prize_places"],
    }


@router.post("/register")
async def register(body: RegisterIn, session: AsyncSession = Depends(get_session)) -> dict:
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
        "message": "Регистрация принята. Депозит от $50 за сегодняшние сутки Dubai попадёт в рейтинг.",
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
            "pnl": dec(r.contest_pnl),
            "return_pct": dec(r.return_pct),
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
    if led and led.last_snapshot_id:
        snap = await session.get(Snapshot, led.last_snapshot_id)
    return {
        "uid": uid,
        "nickname": part.nickname if part else "",
        "registered": part is not None,
        "day": str(day),
        "ledger": row_out(led, snap.ts if snap else None) if led else None,
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
    grouped = {"yield": [], "loss": []}
    for it in items:
        grouped.setdefault(it.nomination, []).append(
            {
                "place": it.place,
                "uid": it.uid,
                "metric": dec(it.metric),
                "pnl": dec(it.pnl),
                "prize_amount": dec(it.prize_amount),
                "prize_note": it.prize_note,
            }
        )
    return {"day": str(day), "frozen": True, "winners": grouped}
