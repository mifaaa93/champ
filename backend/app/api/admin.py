import time

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
import math
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import DayLedger, Participant, Snapshot, RealLeadOverride, Trader
from app.ratelimit import client_ip, limiter
from app.schemas import ProfilePatch, SettingsPatch, ShowcaseIn, day_cash, dec
from app.services.event import list_showcase, save_showcase
from app.services.freeze import freeze_day
from app.services.poll import refresh_statistics, snapshot_watchlist
from app.settings_service import admin_view, get_settings, update_settings
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
    return admin_view(await get_settings(session))


@router.patch("/settings", dependencies=[Depends(require_admin)])
async def patch_settings(
    body: SettingsPatch, session: AsyncSession = Depends(get_session)
) -> dict:
    patch = body.model_dump(exclude_none=True)
    token = patch.get("tg_bot_token")
    if token is not None and not str(token).strip():
        patch.pop("tg_bot_token", None)
    chat = patch.get("tg_chat_id")
    if isinstance(chat, str):
        patch["tg_chat_id"] = chat.strip()
    try:
        saved = await update_settings(session, patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return admin_view(saved)


@router.get("/showcase", dependencies=[Depends(require_admin)])
async def get_showcase(session: AsyncSession = Depends(get_session)) -> dict:
    rows_a = await list_showcase(session, "A")
    rows_b = await list_showcase(session, "B")
    return {"rows": rows_a, "boards": {"A": rows_a, "B": rows_b}}


@router.put("/showcase", dependencies=[Depends(require_admin)])
async def put_showcase(
    body: ShowcaseIn, session: AsyncSession = Depends(get_session)
) -> dict:
    saved: dict[str, list] = {}
    if body.boards:
        for key in ("A", "B"):
            rows = body.boards.get(key)
            if rows is None:
                continue
            saved[key] = await save_showcase(session, rows, key, commit=False)
        await session.commit()
    else:
        code = "B" if str(body.board or "A").upper() == "B" else "A"
        saved[code] = await save_showcase(session, body.rows, code)
    rows_a = saved.get("A") or await list_showcase(session, "A")
    rows_b = saved.get("B") or await list_showcase(session, "B")
    from app.services.event import refresh_event_boards

    await refresh_event_boards(session)
    return {"rows": rows_a, "boards": {"A": rows_a, "B": rows_b}}


@router.get("/real-leads", dependencies=[Depends(require_admin)])
async def list_real_leads(session: AsyncSession = Depends(get_session)) -> dict:
    from app.services.event import real_entries

    entries = await real_entries(session)
    overrides = {
        (r.board, r.uid): r
        for r in (await session.execute(select(RealLeadOverride))).scalars().all()
    }
    rows = []
    for entry in entries:
        for board in ("A", "B"):
            override = overrides.get((board, entry["uid"]))
            rows.append(
                {
                    **entry,
                    "board": board,
                    "frozen": bool(override and override.frozen),
                    "pinned_place": override.pinned_place if override else None,
                    "override": (override.values or {}) if override else {},
                }
            )
    return {"rows": rows}


class RealLeadPatch(BaseModel):
    frozen: bool = False
    pinned_place: int | None = Field(default=None, ge=1, le=20)
    name: str | None = Field(default=None, min_length=1, max_length=64)
    dep: float | None = Field(default=None, ge=0)
    balance: float | None = Field(default=None, ge=0)
    pnl: float | None = None
    return_pct: float | None = None

    @field_validator("dep", "balance", "pnl", "return_pct")
    @classmethod
    def finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("Требуется конечное число")
        return value


@router.patch("/real-leads/{board}/{uid}", dependencies=[Depends(require_admin)])
async def patch_real_lead(
    board: str,
    uid: int,
    body: RealLeadPatch,
    session: AsyncSession = Depends(get_session),
) -> dict:
    if board.upper() not in {"A", "B"}:
        raise HTTPException(422, "Номинация A или B")
    if not (await session.execute(select(Participant.uid).where(Participant.uid == uid))).scalar_one_or_none():
        raise HTTPException(404, "Реальный участник не найден")
    code = "B" if board.upper() == "B" else "A"
    if body.pinned_place is not None:
        taken = (
            await session.execute(
                select(RealLeadOverride.uid).where(
                    RealLeadOverride.board == code,
                    RealLeadOverride.pinned_place == body.pinned_place,
                    RealLeadOverride.uid != uid,
                )
            )
        ).scalar_one_or_none()
        if taken is not None:
            raise HTTPException(409, f"Место {body.pinned_place} уже закреплено за UID {taken}")
    row = await session.get(RealLeadOverride, {"board": code, "uid": uid})
    if row is None:
        row = RealLeadOverride(board=code, uid=uid)
        session.add(row)
    row.frozen = body.frozen
    row.pinned_place = body.pinned_place
    row.values = body.model_dump(exclude_none=True, exclude={"frozen", "pinned_place"})
    await session.commit()
    from app.services.event import refresh_event_boards

    await refresh_event_boards(session)
    return {"ok": True, "board": code, "uid": uid}


class StatisticsPatch(BaseModel):
    mode: str
    players: int = Field(ge=0, le=10_000_000)
    deposits: float = Field(ge=0, le=10_000_000_000)

    @field_validator("deposits")
    @classmethod
    def finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Требуется конечное число")
        return value


async def _live_statistics(session: AsyncSession) -> tuple[int, float]:
    from app.services.event import eligible_real_totals, real_entries

    return eligible_real_totals(await real_entries(session))


def statistics_display(cfg: dict, actual: tuple[int, float]) -> dict:
    offset = cfg.get("stats_offset") or {}
    keys = ("players", "deposits")
    return {
        key: max(0, value + float(offset.get(key) or 0)) if cfg.get("stats_mode") == "editable" else value
        for key, value in zip(keys, actual)
    }


@router.get("/statistics", dependencies=[Depends(require_admin)])
async def get_statistics(session: AsyncSession = Depends(get_session)) -> dict:
    from app.settings_service import get_settings

    cfg = await get_settings(session)
    actual = await _live_statistics(session)
    return {
        "mode": cfg.get("stats_mode", "real"),
        "real": dict(zip(("players", "deposits"), actual)),
        "display": statistics_display(cfg, actual),
    }


@router.patch("/statistics", dependencies=[Depends(require_admin)])
async def patch_statistics(body: StatisticsPatch, session: AsyncSession = Depends(get_session)) -> dict:
    from app.settings_service import update_settings

    if body.mode not in {"real", "editable"}:
        raise HTTPException(422, "Режим: real или editable")
    actual = await _live_statistics(session)
    target = (body.players, body.deposits)
    offset = {key: desired - current for key, desired, current in zip(("players", "deposits"), target, actual)}
    saved = await update_settings(session, {"stats_mode": body.mode, "stats_offset": offset})
    return {**await get_statistics(session), "settings_version": saved["settings_version"]}


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
    from app.telegram import TelegramHtmlError, TelegramSendError

    if kind not in {"hourly", "final"}:
        raise HTTPException(400, "kind: hourly или final")
    try:
        result = await job_publish(kind, force=True)
    except TelegramHtmlError as exc:
        raise HTTPException(status_code=400, detail=exc.errors) from exc
    except TelegramSendError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    label = "итогов дня" if kind == "final" else "часовой"
    status = (result or {}).get("status")
    if status == "skipped":
        return {"ok": False, "status": status, "message": f"Пост {label} не отправлен"}
    if status == "failed":
        raise HTTPException(status_code=400, detail="Telegram не отправлен. Проверь токен бота и ID группы.")
    return {"ok": True, "status": status or "sent", "message": f"Пост {label} отправлен в группу"}


@router.get("/participants", dependencies=[Depends(require_admin)])
async def list_participants(session: AsyncSession = Depends(get_session)) -> dict:
    from app.settings_service import job_get

    day = dubai_today()
    parts = (
        await session.execute(select(Participant).order_by(Participant.created_at.desc()))
    ).scalars().all()
    season = await job_get(session, "event_season")
    api_uids = {
        int(uid) for uid in (season.get("by_uid") or {})
        if str(uid).isdigit()
    }
    known = {p.uid for p in parts}
    trader_rows = (
        await session.execute(select(Trader).where(Trader.uid.in_(api_uids - known)))
    ).scalars().all() if api_uids - known else []
    traders = {r.uid: r for r in trader_rows}
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
                "registered": bool((p.nickname or "").strip()),
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
    for uid in sorted(api_uids - known):
        led = ledgers.get(uid)
        trader = traders.get(uid)
        rows.append({
            "uid": uid,
            "nickname": "",
            "registered": False,
            "telegram": "",
            "country": (trader.country or "") if trader else "",
            "created_at": None,
            "last_checked_at": trader.updated_at.isoformat() if trader and trader.updated_at else None,
            "eligible": False,
            "dq_reason": "not_registered",
            "balance": dec(led.last_balance) if led else None,
            "pnl": dec(led.contest_pnl) if led else None,
            "return_pct": dec(led.return_pct) if led else None,
            "deposits": float((season.get("by_uid") or {}).get(str(uid)) or 0),
        })
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
