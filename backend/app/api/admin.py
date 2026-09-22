import time

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import DayLedger, Participant, Snapshot
from app.ratelimit import client_ip, limiter
from app.schemas import ProfilePatch, SettingsPatch, day_cash, dec
from app.services.freeze import freeze_day
from app.services.poll import refresh_statistics, snapshot_watchlist
from app.settings_service import get_settings, update_settings
from app.timezone import dubai_today

router = APIRouter(prefix="/admin")


async def require_admin(
    request: Request, x_admin_token: str = Header(default="")
) -> None:
    ip = client_ip(request)
    ok, retry = await limiter.allow(f"admin:{ip}", 80, 600)
    if not ok:
        raise HTTPException(status_code=429, detail=f"Слишком много попыток. {retry} с.")
    if not x_admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Неверный токен")


@router.get("/settings", dependencies=[Depends(require_admin)])
async def read_settings(session: AsyncSession = Depends(get_session)) -> dict:
    return await get_settings(session)


@router.patch("/settings", dependencies=[Depends(require_admin)])
async def patch_settings(
    body: SettingsPatch, session: AsyncSession = Depends(get_session)
) -> dict:
    patch = body.model_dump(exclude_none=True)
    return await update_settings(session, patch)


@router.post("/snapshot", dependencies=[Depends(require_admin)])
async def run_snapshot(session: AsyncSession = Depends(get_session)) -> dict:
    stats = await refresh_statistics(session)
    snaps = await snapshot_watchlist(session)
    return {"stats": stats, "snapshots": snaps}


@router.post("/day-close", dependencies=[Depends(require_admin)])
async def day_close(session: AsyncSession = Depends(get_session)) -> dict:
    return await freeze_day(session, dubai_today())


_tg_ctx_cache: dict = {"ts": 0.0, "data": None}
_TG_CTX_TTL = 45.0


@router.get("/telegram-context", dependencies=[Depends(require_admin)])
async def telegram_context(
    session: AsyncSession = Depends(get_session), refresh: bool = Query(False)
) -> dict:
    from app.jobs.runner import telegram_board

    now = time.monotonic()
    cached = _tg_ctx_cache.get("data")
    if not refresh and cached and now - float(_tg_ctx_cache["ts"]) < _TG_CTX_TTL:
        return cached
    data = await telegram_board(session)
    _tg_ctx_cache["data"] = data
    _tg_ctx_cache["ts"] = now
    return data


@router.post("/telegram-send", dependencies=[Depends(require_admin)])
async def telegram_send(kind: str = Query("hourly")) -> dict:
    from app.jobs.runner import job_publish
    from app.telegram import TelegramHtmlError

    if kind not in {"hourly", "final"}:
        raise HTTPException(400, "kind: hourly или final")
    try:
        await job_publish(kind, force=True)
    except TelegramHtmlError as exc:
        raise HTTPException(status_code=400, detail=exc.errors) from exc
    label = "итогов дня" if kind == "final" else "часовой"
    return {"ok": True, "message": f"Пост {label} отправлен в группу"}


@router.get("/participants", dependencies=[Depends(require_admin)])
async def list_participants(session: AsyncSession = Depends(get_session)) -> dict:
    day = dubai_today()
    parts = (
        await session.execute(select(Participant).order_by(Participant.created_at.desc()))
    ).scalars().all()
    ledgers = {
        led.uid: led
        for led in (
            await session.execute(select(DayLedger).where(DayLedger.day == day))
        ).scalars()
    }
    snap_ids = [led.last_snapshot_id for led in ledgers.values() if led.last_snapshot_id]
    snaps = {}
    if snap_ids:
        snaps = {
            s.id: s
            for s in (
                await session.execute(select(Snapshot).where(Snapshot.id.in_(snap_ids)))
            ).scalars()
        }
    rows = []
    for p in parts:
        led = ledgers.get(p.uid)
        last_snap = snaps.get(led.last_snapshot_id) if led and led.last_snapshot_id else None
        last_checked = None
        if last_snap:
            last_checked = last_snap.ts.isoformat()
        elif led and led.updated_at:
            last_checked = led.updated_at.isoformat()
        rows.append(
            {
                "uid": p.uid,
                "nickname": p.nickname or "",
                "telegram": p.telegram or "",
                "country": p.country or "",
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "last_checked_at": last_checked,
                "eligible": bool(led.eligible) if led else False,
                "dq_reason": led.dq_reason if led else "no_start",
                "balance": dec(led.last_balance) if led else None,
                "pnl": dec(led.contest_pnl) if led else None,
                "return_pct": dec(led.return_pct) if led else None,
                "deposits": dec(day_cash(led.day_deposits, led.stats_depo_sum)) if led else None,
            }
        )
    return {"day": str(day), "count": len(rows), "rows": rows}


@router.patch("/participants/{uid}", dependencies=[Depends(require_admin)])
async def patch_participant(
    uid: int, body: ProfilePatch, session: AsyncSession = Depends(get_session)
) -> dict:
    part = (
        await session.execute(select(Participant).where(Participant.uid == uid))
    ).scalar_one_or_none()
    if not part:
        raise HTTPException(404, "Участник не найден")
    part.nickname = body.nickname
    part.telegram = body.telegram
    await session.commit()
    return {"ok": True, "uid": uid, "nickname": part.nickname, "telegram": part.telegram}


@router.delete("/participants/{uid}", dependencies=[Depends(require_admin)])
async def delete_participant(uid: int, session: AsyncSession = Depends(get_session)) -> dict:
    part = (
        await session.execute(select(Participant).where(Participant.uid == uid))
    ).scalar_one_or_none()
    if not part:
        raise HTTPException(404, "Участник не найден")
    day = dubai_today()
    led = (
        await session.execute(
            select(DayLedger).where(DayLedger.day == day, DayLedger.uid == uid)
        )
    ).scalar_one_or_none()
    if led:
        led.registered = False
        led.eligible = False
        led.dq_reason = "not_registered"
    await session.delete(part)
    await session.commit()
    return {"ok": True, "uid": uid, "message": "Участник удалён из чемпионата"}
