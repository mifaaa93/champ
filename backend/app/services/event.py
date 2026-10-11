from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ledger import money
from app.models import Participant, ShowcaseLead, Snapshot, Trader
from app.partners import partners_client
from app.schemas import dec
from app.settings_service import get_settings, job_get, job_set
from app.timezone import now_champ

DEFAULT_SHOWCASE = [
    {"place": 1, "name": "Ахмед", "dep": 150000, "turn": 4500000},
    {"place": 2, "name": "Равшан", "dep": 120000, "turn": 3800000},
    {"place": 3, "name": "Джамшут", "dep": 95000, "turn": 2900000},
    {"place": 4, "name": "Тимур", "dep": 82000, "turn": 2400000},
    {"place": 5, "name": "Азамат", "dep": 74000, "turn": 2100000},
    {"place": 6, "name": "Руслан", "dep": 65000, "turn": 1800000},
    {"place": 7, "name": "Бахтиёр", "dep": 58000, "turn": 1500000},
    {"place": 8, "name": "Фарход", "dep": 49000, "turn": 1200000},
    {"place": 9, "name": "Шерзод", "dep": 42000, "turn": 950000},
    {"place": 10, "name": "Улугбек", "dep": 35000, "turn": 800000},
]


def dummy_uid(place: int) -> int:
    return -int(place)


def sort_by_dep(entries: list[dict]) -> list[dict]:
    ordered = sorted(
        entries,
        key=lambda r: (
            -float(r.get("dep") or 0),
            1 if r.get("dummy") else 0,
            int(r.get("uid") or 0),
        ),
    )
    out = []
    for i, row in enumerate(ordered, 1):
        item = dict(row)
        item["rank"] = i
        out.append(item)
    return out


def merge_board(dummies: list[dict], reals: list[dict]) -> list[dict]:
    entries: list[dict] = []
    for d in dummies:
        place = int(d.get("place") or 0)
        entries.append(
            {
                "uid": dummy_uid(place) if place else int(d.get("uid") or 0),
                "name": str(d.get("name") or "Лид"),
                "dep": float(d.get("dep") or 0),
                "turn": float(d.get("turn") or 0),
                "dummy": True,
            }
        )
    seen: set[int] = set()
    for r in reals:
        uid = int(r.get("uid") or 0)
        if uid <= 0 or uid in seen:
            continue
        seen.add(uid)
        entries.append(
            {
                "uid": uid,
                "name": str(r.get("name") or "Трейдер"),
                "dep": float(r.get("dep") or 0),
                "turn": float(r.get("turn") or 0),
                "dummy": False,
            }
        )
    return sort_by_dep(entries)


def overtake_events(old: list[dict], new: list[dict]) -> list[dict]:
    if not old:
        return []
    old_rank = {int(r["uid"]): int(r["rank"]) for r in old if r.get("uid") is not None}
    events: list[dict] = []
    for row in new:
        if row.get("dummy"):
            continue
        uid = int(row["uid"])
        prev = old_rank.get(uid)
        if prev is None:
            events.append(
                {
                    "name": row["name"],
                    "action": "вошёл в турнир",
                    "extra": "",
                    "rank": row["rank"],
                }
            )
            passed = [
                x
                for x in new
                if int(x["rank"]) > int(row["rank"]) and old_rank.get(int(x["uid"]), 10**9) < 10**9
            ]
            dummy_passed = next((x for x in passed if x.get("dummy")), None)
            if dummy_passed and int(row["rank"]) <= 10:
                events.append(
                    {
                        "name": row["name"],
                        "action": "обогнал",
                        "extra": dummy_passed["name"],
                        "rank": row["rank"],
                    }
                )
            continue
        if int(row["rank"]) >= prev:
            continue
        passed = [
            x
            for x in new
            if int(x["rank"]) > int(row["rank"]) and old_rank.get(int(x["uid"]), 10**9) < prev
        ]
        target = next((x for x in passed if x.get("dummy")), passed[0] if passed else None)
        if target:
            events.append(
                {
                    "name": row["name"],
                    "action": "обогнал",
                    "extra": target["name"],
                    "rank": row["rank"],
                }
            )
        else:
            events.append(
                {
                    "name": row["name"],
                    "action": "поднялся на",
                    "extra": "",
                    "rank": row["rank"],
                }
            )
    return events


def board_totals(board: list[dict]) -> tuple[int, float]:
    players = len(board)
    turnover = sum(float(r.get("turn") or 0) for r in board)
    return players, turnover


def activity_time_label(ts: float, now: float) -> str:
    sec = max(0, int(now - ts))
    if sec < 45:
        return "только что"
    if sec < 3600:
        return f"{max(1, sec // 60)} мин назад"
    if sec < 86400:
        return f"{max(1, sec // 3600)} ч назад"
    return f"{max(1, sec // 86400)} дн назад"


def neighbor_window(ranked: list[dict], uid: int, span: int = 2) -> list[dict]:
    idx = next((i for i, r in enumerate(ranked) if int(r["uid"]) == int(uid)), None)
    if idx is None:
        return []
    start = max(0, idx - span)
    end = min(len(ranked), idx + span + 1)
    return ranked[start:end]


def turnover_from_info(info: dict | None) -> float:
    if not info:
        return 0.0
    for key in ("turnover", "volume", "trading_volume", "sum_turnover", "turnover_30d"):
        if info.get(key) is not None:
            try:
                return float(info[key])
            except (TypeError, ValueError):
                continue
    return 0.0


async def ensure_showcase(session: AsyncSession) -> None:
    count = (await session.execute(select(func.count()).select_from(ShowcaseLead))).scalar_one()
    if count:
        return
    for row in DEFAULT_SHOWCASE:
        session.add(
            ShowcaseLead(
                place=int(row["place"]),
                name=str(row["name"]),
                dep=money(row["dep"]),
                turn=money(row["turn"]),
            )
        )
    await session.commit()


async def list_showcase(session: AsyncSession) -> list[dict]:
    await ensure_showcase(session)
    rows = (
        await session.execute(select(ShowcaseLead).order_by(ShowcaseLead.place))
    ).scalars().all()
    return [
        {
            "place": r.place,
            "name": r.name,
            "dep": dec(r.dep),
            "turn": dec(r.turn),
            "uid": r.uid,
        }
        for r in rows
    ]


async def save_showcase(session: AsyncSession, rows: list[dict]) -> list[dict]:
    if len(rows) != 10:
        raise HTTPException(400, "Нужно ровно 10 мест витрины")
    places = [int(r.get("place") or 0) for r in rows]
    if sorted(places) != list(range(1, 11)):
        raise HTTPException(400, "Места витрины должны быть 1–10 без повторов")
    existing = {
        r.place: r
        for r in (await session.execute(select(ShowcaseLead))).scalars()
    }
    for raw in rows:
        place = int(raw["place"])
        name = str(raw.get("name") or "").strip()[:64]
        if not name:
            raise HTTPException(400, f"Имя для места {place} пустое")
        dep = money(raw.get("dep") or 0)
        turn = money(raw.get("turn") or 0)
        uid = raw.get("uid")
        uid_i = int(uid) if uid else None
        row = existing.get(place)
        if row is None:
            row = ShowcaseLead(place=place)
            session.add(row)
        row.name = name
        row.dep = dep
        row.turn = turn
        row.uid = uid_i
    await session.commit()
    return await list_showcase(session)


async def public_event(session: AsyncSession) -> dict:
    cfg = await get_settings(session)
    end = str(cfg.get("event_end") or "")
    if not end:
        end = (now_champ() + timedelta(days=14)).isoformat()
    board, live = await refresh_event_board(session)
    now = now_champ().timestamp()
    players, turnover = board_totals(board)
    return {
        "name": cfg.get("event_name") or "PO TOURNAMENT",
        "event_end": end,
        "prize_pool": float(cfg.get("prize_pool") or 0),
        "prize_table": cfg.get("prize_table") or [],
        "stats_players": players,
        "stats_turnover": turnover,
        "telegram_channel_url": cfg.get("telegram_channel_url") or "",
        "rami_url": cfg.get("rami_url") or "",
        "rules": cfg.get("event_rules") or [],
        "activity": _format_activity(live, cfg.get("activity") or [], now),
        "top": _public_top(board),
    }


async def _latest_snaps(session: AsyncSession, uids: list[int]) -> dict[int, Snapshot]:
    if not uids:
        return {}
    sub = (
        select(Snapshot.uid, func.max(Snapshot.ts).label("ts"))
        .where(Snapshot.uid.in_(uids))
        .group_by(Snapshot.uid)
        .subquery()
    )
    rows = (
        await session.execute(
            select(Snapshot).join(
                sub, (Snapshot.uid == sub.c.uid) & (Snapshot.ts == sub.c.ts)
            )
        )
    ).scalars().all()
    return {s.uid: s for s in rows}


async def real_entries(session: AsyncSession) -> list[dict]:
    parts = (await session.execute(select(Participant))).scalars().all()
    snaps = await _latest_snaps(session, [p.uid for p in parts])
    traders = {}
    if parts:
        traders = {
            t.uid: t
            for t in (
                await session.execute(
                    select(Trader).where(Trader.uid.in_([p.uid for p in parts]))
                )
            ).scalars()
        }
    entries = []
    for p in parts:
        snap = snaps.get(p.uid)
        trader = traders.get(p.uid)
        info = (trader.last_user_info if trader else None) or (snap.raw if snap else None) or {}
        dep = float(snap.sum_deposits) if snap else 0.0
        turn = turnover_from_info(info if isinstance(info, dict) else None)
        entries.append(
            {
                "uid": p.uid,
                "name": p.nickname or "Трейдер",
                "dep": dep,
                "turn": turn,
                "dummy": False,
            }
        )
    return entries


async def ranked_board(session: AsyncSession) -> list[dict]:
    return merge_board(await list_showcase(session), await real_entries(session))


async def refresh_event_board(session: AsyncSession) -> tuple[list[dict], list[dict]]:
    board = await ranked_board(session)
    state = await job_get(session, "event_live")
    old = state.get("board") or []
    events = overtake_events(old, board)
    now = now_champ().timestamp()
    live = list(state.get("activity") or [])
    for ev in reversed(events):
        live.insert(0, {**ev, "ts": now})
    live = live[:20]
    slim = [
        {
            "uid": r["uid"],
            "name": r["name"],
            "dep": r["dep"],
            "rank": r["rank"],
            "dummy": bool(r.get("dummy")),
        }
        for r in board[:80]
    ]
    await job_set(session, "event_live", {"board": slim, "activity": live})
    return board, live


def _public_top(board: list[dict]) -> list[dict]:
    out = []
    for r in board[:10]:
        out.append(
            {
                "place": r["rank"],
                "name": r["name"],
                "dep": r["dep"],
                "turn": r.get("turn") or 0,
                "dummy": bool(r.get("dummy")),
            }
        )
    return out


def _format_activity(live: list[dict], seeded: list[dict], now: float) -> list[dict]:
    out = []
    for row in live:
        item = {
            "name": row.get("name") or "",
            "action": row.get("action") or "",
            "extra": row.get("extra") or "",
            "rank": row.get("rank"),
            "time": activity_time_label(float(row.get("ts") or now), now),
        }
        out.append(item)
    if len(out) < 5:
        for row in seeded:
            out.append(
                {
                    "name": row.get("name") or "",
                    "action": row.get("action") or "",
                    "extra": row.get("extra") or "",
                    "rank": row.get("rank"),
                    "time": row.get("time") or "",
                }
            )
            if len(out) >= 8:
                break
    return out[:8]


def _profile_payload(ranked: list[dict], uid: int, stats_players: int | None = None) -> dict | None:
    me = next((r for r in ranked if int(r["uid"]) == int(uid)), None)
    if me is None:
        return None
    total = stats_players if stats_players is not None else len(ranked)
    total = max(total, len(ranked), me["rank"])
    beaten = max(0, total - me["rank"])
    neighbors = []
    for row in neighbor_window(ranked, uid, 2):
        dummy = bool(row.get("dummy"))
        neighbors.append(
            {
                "rank": row["rank"],
                "uid": 0 if dummy else row["uid"],
                "name": row["name"],
                "dep": row["dep"],
                "dummy": dummy,
                "is_you": (not dummy) and int(row["uid"]) == int(uid),
            }
        )
    return {
        "uid": me["uid"],
        "name": me["name"],
        "rank": me["rank"],
        "dep": me["dep"],
        "turn": me["turn"],
        "beaten": beaten,
        "total": total,
        "neighbors": neighbors,
    }


async def lookup_event_uid(session: AsyncSession, uid: int) -> dict:
    if uid < 100_000_000 or uid > 9_999_999_999:
        raise HTTPException(400, "format")
    try:
        info = await partners_client.user_info(uid)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Проверка UID временно недоступна") from exc
    if not info:
        return {"uid": uid, "status": "not_in_base"}

    part = (
        await session.execute(select(Participant).where(Participant.uid == uid))
    ).scalar_one_or_none()
    if not part or not (part.nickname or "").strip():
        return {"uid": uid, "status": "need_name"}

    try:
        from app.services.poll import snapshot_uid

        await snapshot_uid(session, uid)
    except Exception:
        pass
    cfg = await get_settings(session)
    board, _live = await refresh_event_board(session)
    profile = _profile_payload(board, uid)
    return {"uid": uid, "status": "ok", "you": profile}


async def register_event_name(
    session: AsyncSession, uid: int, nickname: str
) -> dict:
    check = await lookup_event_uid(session, uid)
    if check["status"] == "not_in_base":
        raise HTTPException(status_code=404, detail="not_in_base")
    if check["status"] == "ok" and check.get("you"):
        return check

    nick = nickname.strip()[:64]
    part = (
        await session.execute(select(Participant).where(Participant.uid == uid))
    ).scalar_one_or_none()
    try:
        info = await partners_client.user_info(uid)
    except httpx.HTTPError:
        info = None
    if part is None:
        part = Participant(
            uid=uid,
            nickname=nick,
            country=(info or {}).get("country") if isinstance(info, dict) else None,
        )
        session.add(part)
    else:
        part.nickname = nick
    await session.commit()

    try:
        from app.services.poll import snapshot_uid

        await snapshot_uid(session, uid)
    except Exception:
        pass

    cfg = await get_settings(session)
    board, _live = await refresh_event_board(session)
    profile = _profile_payload(board, uid)
    if profile is None:
        total = max(1, len(board))
        profile = {
            "uid": uid,
            "name": nick,
            "rank": total,
            "dep": 0.0,
            "turn": 0.0,
            "beaten": 0,
            "total": total,
            "neighbors": [
                {"rank": 1, "uid": uid, "name": nick, "dep": 0.0, "is_you": True}
            ],
        }
    return {"uid": uid, "status": "ok", "you": profile}


async def invite_preview(session: AsyncSession, uid: int) -> dict:
    part = (
        await session.execute(select(Participant).where(Participant.uid == uid))
    ).scalar_one_or_none()
    if not part or not (part.nickname or "").strip():
        raise HTTPException(404, "not found")
    cfg = await get_settings(session)
    board, _live = await refresh_event_board(session)
    profile = _profile_payload(board, uid)
    if not profile:
        raise HTTPException(404, "not found")
    return {
        "uid": uid,
        "name": profile["name"],
        "rank": profile["rank"],
        "dep": profile["dep"],
    }
