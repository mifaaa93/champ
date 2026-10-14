from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ledger import money, return_pct
from app.models import DayLedger, Participant, ShowcaseLead, Snapshot, Trader
from app.partners import partners_client
from app.schemas import dec
from app.settings_service import get_settings, job_get, job_set
from app.timezone import CHAMP_TZ, champ_today, now_champ

log = logging.getLogger("champ.event")

DUMMY_NAMES = [
    "Ахмед",
    "Равшан",
    "Джамшут",
    "Тимур",
    "Азамат",
    "Руслан",
    "Бахтиёр",
    "Фарход",
    "Шерзод",
    "Улугбек",
    "Нурлан",
    "Ерлан",
    "Санжар",
    "Бекзод",
    "Алишер",
    "Камран",
    "Мурат",
    "Ойбек",
    "Жасур",
    "Дилшод",
    "Александр",
    "Дмитрий",
    "Максим",
    "Сергей",
    "Андрей",
    "Алексей",
    "Артём",
    "Илья",
    "Кирилл",
    "Михаил",
]


def _seed_row(place: int, name: str, dep: float, turn: float, pnl: float) -> dict:
    return {
        "place": place,
        "name": name,
        "dep": dep,
        "pnl": pnl,
        "balance": dep + pnl,
        "return_pct": round((pnl / dep) * 100, 2) if dep else 0,
    }


DEFAULT_SHOWCASE = [
    _seed_row(1, "Ахмед", 150000, 4500000, 12500),
    _seed_row(2, "Равшан", 120000, 3800000, 5100),
    _seed_row(3, "Джамшут", 95000, 2900000, 3000),
    _seed_row(4, "Тимур", 82000, 2400000, 4800),
    _seed_row(5, "Азамат", 74000, 2100000, 1500),
    _seed_row(6, "Руслан", 65000, 1800000, 2250),
    _seed_row(7, "Бахтиёр", 58000, 1500000, 2500),
    _seed_row(8, "Фарход", 49000, 1200000, 1200),
    _seed_row(9, "Шерзод", 42000, 950000, 600),
    _seed_row(10, "Улугбек", 35000, 800000, 600),
]

DEFAULT_SHOWCASE_B = [
    _seed_row(1, "Нурлан", 140000, 4200000, -18000),
    _seed_row(2, "Ерлан", 118000, 3600000, -14200),
    _seed_row(3, "Санжар", 97000, 3100000, -11000),
    _seed_row(4, "Бекзод", 86000, 2700000, -8900),
    _seed_row(5, "Алишер", 76000, 2300000, -7200),
    _seed_row(6, "Камран", 68000, 1900000, -5600),
    _seed_row(7, "Мурат", 59000, 1600000, -4300),
    _seed_row(8, "Ойбек", 51000, 1300000, -3100),
    _seed_row(9, "Жасур", 44000, 1000000, -2100),
    _seed_row(10, "Дилшод", 38000, 850000, -1400),
]

SHOWCASE_SEEDS = {"A": DEFAULT_SHOWCASE, "B": DEFAULT_SHOWCASE_B}


def board_code(value: str | None) -> str:
    return "B" if str(value or "A").strip().upper() == "B" else "A"


def dummy_uid(place: int, board: str = "A") -> int:
    slot = int(place)
    if board_code(board) == "B":
        return -(100 + slot)
    return -slot


def visible_nominations(cfg: dict) -> tuple[bool, bool]:
    show_a = bool(cfg.get("show_nomination_a", True))
    show_b = bool(cfg.get("show_nomination_b", True))
    if not show_a and not show_b:
        return True, True
    return show_a, show_b


def parse_event_dt(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CHAMP_TZ)
    return dt.astimezone(CHAMP_TZ)


def event_bounds(cfg: dict) -> tuple[datetime, datetime]:
    now = now_champ()
    end = parse_event_dt(cfg.get("event_end")) or (now + timedelta(days=14))
    start = parse_event_dt(cfg.get("event_start")) or (end - timedelta(days=14))
    if start > end:
        start, end = end, start
    return start, end


def min_event_deposit(cfg: dict) -> float:
    return float(cfg.get("event_min_deposit") or cfg.get("min_day_deposit") or 50)


def season_dep_from_points(
    points: list[tuple[datetime, float]], start: datetime, end: datetime
) -> float:
    if not points:
        return 0.0
    ordered = sorted(points, key=lambda p: p[0])
    before = [p for p in ordered if p[0] <= start]
    upto = [p for p in ordered if p[0] <= end]
    if not upto and not before:
        return 0.0
    opening = before[-1][1] if before else upto[0][1]
    last = upto[-1][1] if upto else opening
    return max(0.0, float(last) - float(opening))


def season_deposit_delta(
    before: float | None,
    earliest: float | None,
    latest: float | None,
) -> float | None:
    """Season deposit visible from snapshot boundaries.

    A pre-start baseline plus the last in-season snapshot is the full delta.
    Without a baseline, only the rise between two different in-season
    snapshots is known. One lifetime sum cannot be turned into a deposit.
    """
    if before is not None and latest is not None:
        return max(0.0, float(latest) - float(before))
    if (
        earliest is not None
        and latest is not None
        and float(latest) != float(earliest)
    ):
        return max(0.0, float(latest) - float(earliest))
    return None


def nudge_amount(value: float, rng: random.Random, lo: float = 50.0, hi: float = 500_000.0) -> float:
    factor = rng.uniform(0.97, 1.07)
    return round(max(lo, min(hi, float(value) * factor)), 2)


def pick_dummy_name(current: str, taken: set[str], rng: random.Random) -> str:
    options = [n for n in DUMMY_NAMES if n not in taken and n != current]
    if not options:
        options = [n for n in DUMMY_NAMES if n != current]
    if not options:
        return current
    return rng.choice(options)


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
                "balance": float(d.get("balance") or 0),
                "pnl": float(d.get("pnl") or 0),
                "return_pct": float(d.get("return_pct") or 0),
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
                "balance": float(r.get("balance") or 0),
                "pnl": float(r.get("pnl") or 0),
                "return_pct": float(r.get("return_pct") or 0),
                "dummy": False,
            }
        )
    return sort_by_dep(entries)


def _stamp_ranks(ordered: list[dict]) -> list[dict]:
    out = []
    for i, row in enumerate(ordered, 1):
        item = dict(row)
        item["rank"] = i
        out.append(item)
    return out


def sort_by_yield(entries: list[dict]) -> list[dict]:
    ordered = sorted(
        entries,
        key=lambda r: (
            -float(r.get("return_pct") or 0),
            -float(r.get("pnl") or 0),
            1 if r.get("dummy") else 0,
            int(r.get("uid") or 0),
        ),
    )
    return _stamp_ranks(ordered)


def sort_by_loss(entries: list[dict]) -> list[dict]:
    ordered = sorted(
        entries,
        key=lambda r: (
            float(r.get("pnl") or 0),
            float(r["trading_return_pct"]) if r.get("trading_return_pct") is not None else 0.0,
            1 if r.get("dummy") else 0,
            int(r.get("uid") or 0),
        ),
    )
    return _stamp_ranks(ordered)


def merge_nomination(dummies: list[dict], reals: list[dict], board: str) -> list[dict]:
    code = board_code(board)
    entries: list[dict] = []
    for d in dummies:
        if d.get("hidden"):
            continue
        place = int(d.get("place") or 0)
        entries.append(
            {
                "uid": dummy_uid(place, code) if place else int(d.get("uid") or 0),
                "name": str(d.get("name") or "Лид"),
                "dep": float(d.get("dep") or 0),
                "turn": float(d.get("turn") or 0),
                "balance": float(d.get("balance") or 0),
                "pnl": float(d.get("pnl") or 0),
                "return_pct": float(d.get("return_pct") or 0),
                "dummy": True,
                "board": code,
            }
        )
    seen: set[int] = set()
    for r in reals:
        uid = int(r.get("uid") or 0)
        if uid <= 0 or uid in seen:
            continue
        if r.get("blocked"):
            continue
        if code == "B":
            shown = r.get("trading_pnl")
            pnl = float(shown if shown is not None else r.get("pnl") or 0)
            if pnl >= 0 and not r.get("force_nomination"):
                continue
            ret = r.get("trading_return_pct")
        else:
            pnl = float(r.get("pnl") or 0)
            if pnl <= 0 and not r.get("force_nomination"):
                continue
            ret = r.get("return_pct")
        seen.add(uid)
        entries.append(
            {
                "uid": uid,
                "name": str(r.get("name") or "Трейдер"),
                "dep": float(r.get("dep") or 0),
                "turn": float(r.get("turn") or 0),
                "balance": float(r.get("balance") or 0),
                "pnl": pnl,
                "return_pct": float(ret or 0),
                "trading_return_pct": float(r.get("trading_return_pct") or 0),
                "dummy": False,
                "board": code,
            }
        )
    return sort_by_loss(entries) if code == "B" else sort_by_yield(entries)


def place_pinned(ordered: list[dict], pins: dict[int, int]) -> list[dict]:
    """Keep pinned places even when there are too few entrants to fill preceding slots."""
    reserved: dict[int, dict] = {}
    rest: list[dict] = []
    for row in ordered:
        place = pins.get(int(row["uid"])) if not row.get("dummy") else None
        if place is not None and place > 0 and place not in reserved:
            reserved[place] = row
        else:
            rest.append(row)
    positions = dict(reserved)
    place = 1
    for row in rest:
        while place in positions:
            place += 1
        positions[place] = row
        place += 1
    return [{**row, "rank": rank} for rank, row in sorted(positions.items())]


TRACKED_RANKS = 80


def overtake_events(old: list[dict], new: list[dict]) -> list[dict]:
    if not old:
        return []
    # The saved board is only the tracked window. Ranks outside it must not
    # look like a fresh entry on every refresh.
    old = list(old)[:TRACKED_RANKS]
    new = [r for r in new if int(r.get("rank") or 0) <= TRACKED_RANKS]
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


def dummy_live_events(old: list[dict], new: list[dict]) -> list[dict]:
    if not old:
        return []
    old_map = {int(r["uid"]): r for r in old if r.get("dummy") and r.get("uid") is not None}
    events: list[dict] = []
    for row in new:
        if not row.get("dummy"):
            continue
        prev = old_map.get(int(row["uid"]))
        if not prev:
            continue
        if str(prev.get("name") or "") != str(row.get("name") or ""):
            events.append(
                {
                    "name": row["name"],
                    "action": "занял место",
                    "extra": "",
                    "rank": row["rank"],
                }
            )
            continue
        if int(row["rank"]) < int(prev.get("rank") or row["rank"]):
            events.append(
                {
                    "name": row["name"],
                    "action": "поднялся на",
                    "extra": "",
                    "rank": row["rank"],
                }
            )
            continue
        delta = float(row.get("dep") or 0) - float(prev.get("dep") or 0)
        if delta >= max(50.0, float(prev.get("dep") or 0) * 0.008):
            events.append(
                {
                    "name": row["name"],
                    "action": "пополнил депозит на",
                    "extra": f"${int(round(delta)):,}".replace(",", " "),
                    "rank": None,
                }
            )
    return events[:3]


def board_totals(board: list[dict]) -> tuple[int, float, float]:
    players = len(board)
    deposits = sum(float(r.get("dep") or 0) for r in board)
    turnover = sum(float(r.get("turn") or 0) for r in board)
    return players, deposits, turnover


def combined_totals(boards: list[list[dict]]) -> tuple[int, float, float]:
    seen_real: set[int] = set()
    players = 0
    deposits = 0.0
    turnover = 0.0
    for board in boards:
        for row in board:
            if row.get("dummy"):
                players += 1
                deposits += float(row.get("dep") or 0)
                turnover += float(row.get("turn") or 0)
                continue
            uid = int(row.get("uid") or 0)
            if uid in seen_real:
                continue
            seen_real.add(uid)
            players += 1
            deposits += float(row.get("dep") or 0)
            turnover += float(row.get("turn") or 0)
    return players, deposits, turnover


def real_totals(boards: list[list[dict]]) -> tuple[int, float]:
    players, deposits, _turnover = combined_totals(
        [[row for row in board if not row.get("dummy")] for board in boards]
    )
    return players, deposits


def eligible_real_totals(entries: list[dict]) -> tuple[int, float]:
    """Statistics of registered, deposit-qualified traders."""
    eligible = {int(row["uid"]): row for row in entries if row.get("in_ranking")}
    return len(eligible), sum(float(row.get("dep") or 0) for row in eligible.values())


def event_totals(boards: list[list[dict]], entries: list[dict]) -> tuple[int, float]:
    """Count configured demo slots plus eligible real traders, without double-counting reals."""
    dummy_count = sum(1 for board in boards for row in board if row.get("dummy"))
    dummy_deposits = sum(
        float(row.get("dep") or 0) for board in boards for row in board if row.get("dummy")
    )
    real_count, real_deposits = eligible_real_totals(entries)
    return dummy_count + real_count, dummy_deposits + real_deposits


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


def _showcase_out(row: ShowcaseLead) -> dict:
    return {
        "board": board_code(getattr(row, "board", "A")),
        "place": row.place,
        "name": row.name,
        "dep": dec(row.dep),
        "balance": dec(getattr(row, "balance", 0)),
        "pnl": dec(getattr(row, "pnl", 0)),
        "return_pct": dec(getattr(row, "return_pct", 0)),
        "uid": row.uid,
        "randomize": bool(getattr(row, "randomize", True)),
        "hidden": bool(getattr(row, "hidden", False)),
    }


async def ensure_showcase(session: AsyncSession) -> None:
    added = False
    for code, seed in SHOWCASE_SEEDS.items():
        count = (
            await session.execute(
                select(func.count()).select_from(ShowcaseLead).where(ShowcaseLead.board == code)
            )
        ).scalar_one()
        if count:
            continue
        for row in seed:
            session.add(
                ShowcaseLead(
                    board=code,
                    place=int(row["place"]),
                    name=str(row["name"]),
                    dep=money(row["dep"]),
                    turn=money(row["turn"]),
                    balance=money(row.get("balance") or 0),
                    pnl=money(row.get("pnl") or 0),
                    return_pct=money(row.get("return_pct") or 0),
                    randomize=True,
                )
            )
        added = True
    if added:
        await session.commit()


async def list_showcase(session: AsyncSession, board: str | None = None) -> list[dict]:
    await ensure_showcase(session)
    stmt = select(ShowcaseLead).order_by(ShowcaseLead.board, ShowcaseLead.place)
    if board:
        stmt = stmt.where(ShowcaseLead.board == board_code(board))
    rows = (await session.execute(stmt)).scalars().all()
    return [_showcase_out(r) for r in rows]


def _finite_amount(value: object, label: str):
    try:
        dec = money(0 if value is None or value == "" else value)
    except Exception as exc:
        raise HTTPException(422, f"{label}: нужно число") from exc
    if not dec.is_finite():
        raise HTTPException(422, f"{label}: нужно конечное число")
    return dec


async def save_showcase(
    session: AsyncSession, rows: list[dict], board: str = "A", *, commit: bool = True
) -> list[dict]:
    code = board_code(board)
    if len(rows) != 10:
        raise HTTPException(400, "Нужно ровно 10 мест витрины")
    places = [int(r.get("place") or 0) for r in rows]
    if sorted(places) != list(range(1, 11)):
        raise HTTPException(400, "Места витрины должны быть 1–10 без повторов")
    existing = {
        r.place: r
        for r in (
            await session.execute(select(ShowcaseLead).where(ShowcaseLead.board == code))
        ).scalars()
    }
    for raw in rows:
        place = int(raw["place"])
        name = str(raw.get("name") or "").strip()[:64]
        if not name:
            raise HTTPException(400, f"Имя для места {place} пустое")
        uid = raw.get("uid")
        try:
            uid_i = int(uid) if uid else None
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, f"UID места {place}: нужно число") from exc
        row = existing.get(place)
        if row is None:
            row = ShowcaseLead(board=code, place=place)
            session.add(row)
        row.board = code
        row.name = name
        row.dep = _finite_amount(raw.get("dep"), f"Депозит места {place}")
        row.turn = money(0)
        row.balance = _finite_amount(raw.get("balance"), f"Баланс места {place}")
        row.pnl = _finite_amount(raw.get("pnl"), f"Прибыль места {place}")
        row.return_pct = _finite_amount(raw.get("return_pct"), f"Доходность места {place}")
        row.uid = uid_i
        row.randomize = bool(raw.get("randomize", True))
        row.hidden = bool(raw.get("hidden", False))
    await session.flush()
    if commit:
        await session.commit()
    return await list_showcase(session, code)


async def public_event(session: AsyncSession, uid: int | None = None) -> dict:
    cfg = await get_settings(session)
    start, end = event_bounds(cfg)
    state = await job_get(session, "event_live")
    if state.get("ranks_a") is None or state.get("ranks_b") is None:
        await refresh_event_boards(session)
        state = await job_get(session, "event_live")
    board_a = list(state.get("ranks_a") or [])
    board_b = list(state.get("ranks_b") or [])
    live = list(state.get("activity") or [])
    now = now_champ().timestamp()
    show_a, show_b = visible_nominations(cfg)
    real = await real_entries(session)
    visible_boards = [board for board, visible in ((board_a, show_a), (board_b, show_b)) if visible]
    players, deposits = event_totals(visible_boards, real)
    if cfg.get("stats_mode") == "editable":
        offset = cfg.get("stats_offset") or {}
        players = max(0, players + int(offset.get("players") or 0))
        deposits = max(0.0, deposits + float(offset.get("deposits") or 0))
    top_a = _public_top(board_a, int(cfg.get("top_visible") or 10))
    top_b = _public_top(board_b, int(cfg.get("top_visible") or 10))
    you = None
    if uid:
        you = _dual_profile(board_a, board_b, uid, players)
        if you is None:
            me = next((r for r in real if int(r["uid"]) == int(uid)), None)
            if me and (me.get("name") or "").strip():
                you = _unranked_profile(
                    uid,
                    me["name"],
                    float(me["dep"]),
                    min_event_deposit(cfg),
                    len(board_a),
                    float(me.get("balance") or 0),
                    float(me.get("pnl") or 0),
                    float(me.get("return_pct") or 0),
                )
    return {
        "name": cfg.get("event_name") or "PO CHAMPIONSHIP",
        "event_start": start.isoformat(),
        "event_end": end.isoformat(),
        "min_deposit": min_event_deposit(cfg),
        "top_visible": int(cfg.get("top_visible") or 10),
        "prize_pool": float(cfg.get("prize_pool") or 0),
        "prize_table": cfg.get("prize_table") or [],
        "stats_players": players,
        "stats_deposits": deposits,
        "telegram_channel_url": cfg.get("telegram_channel_url") or "",
        "rami_url": cfg.get("rami_url") or "",
        "rules": [
            rule for rule in (cfg.get("event_rules") or [])
            if rule != "Оборот учитывается за последние 30 дней активности, если данные есть в базе."
        ],
        "activity": _format_activity(live, now),
        "show_a": show_a,
        "show_b": show_b,
        "top_a": top_a,
        "top_b": top_b,
        "top": top_a if show_a else top_b,
        "metrics": await day_metrics(session, cfg),
        "you": you,
    }


async def day_metrics(session: AsyncSession, cfg: dict) -> dict:
    from app.services.freeze import load_rank_rows
    from app.services.ranking import loss_pool, yield_pool

    day = champ_today()
    rows = await load_rank_rows(session, day)
    top_n = int(cfg.get("top_n") or 7)
    y = yield_pool(rows)[:top_n]
    loss = loss_pool(rows)[:top_n]

    def pack(seq, *, is_loss: bool = False) -> list[dict]:
        out = []
        for i, r in enumerate(seq, 1):
            out.append(
                {
                    "place": i,
                    "name": r.nickname or "Трейдер",
                    "pct": float(r.trading_return_pct if is_loss else r.return_pct),
                    "pnl": float(r.trading_pnl if is_loss else r.contest_pnl),
                }
            )
        return out

    return {"day": str(day), "yield": pack(y), "loss": pack(loss, is_loss=True)}


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


async def _snaps_at_or_before(
    session: AsyncSession, uids: list[int], ts: datetime
) -> dict[int, Snapshot]:
    if not uids:
        return {}
    sub = (
        select(Snapshot.uid, func.max(Snapshot.ts).label("ts"))
        .where(Snapshot.uid.in_(uids), Snapshot.ts <= ts)
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


async def _first_snap_between(
    session: AsyncSession, uids: list[int], start: datetime, end: datetime
) -> dict[int, Snapshot]:
    if not uids:
        return {}
    sub = (
        select(Snapshot.uid, func.min(Snapshot.ts).label("ts"))
        .where(Snapshot.uid.in_(uids), Snapshot.ts > start, Snapshot.ts <= end)
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


def _season_cache_ok(raw: dict, start: datetime, end: datetime) -> bool:
    return (
        raw.get("from") == start.date().isoformat()
        and raw.get("end") == end.date().isoformat()
    )


async def refresh_season_statistics(session: AsyncSession) -> dict:
    cfg = await get_settings(session)
    start, end = event_bounds(cfg)
    through = min(champ_today(), end.date())
    if through < start.date():
        through = start.date()
    payload = await partners_client.statistics_range(start.date().isoformat(), through.isoformat())
    old = await job_get(session, "event_season")
    if payload.get("truncated"):
        log.error("season statistics truncated; previous cache kept")
        return {"skipped": True, "reason": "truncated"}
    rows = payload.get("data")
    if not rows and _season_cache_ok(old, start, end) and old.get("by_uid"):
        log.error("season statistics empty; previous cache kept")
        return {"skipped": True, "reason": "empty"}
    by_uid: dict[str, float] = {}
    for row in rows or []:
        try:
            uid = int(row.get("group1"))
        except (TypeError, ValueError):
            continue
        by_uid[str(uid)] = float(row.get("depo_sum") or 0)
    state = {
        "from": start.date().isoformat(),
        "end": end.date().isoformat(),
        "through": through.isoformat(),
        "by_uid": by_uid,
    }
    await job_set(session, "event_season", state)
    return {"from": state["from"], "through": state["through"], "uids": len(by_uid)}


async def real_entries(session: AsyncSession) -> list[dict]:
    cfg = await get_settings(session)
    start, end = event_bounds(cfg)
    through = min(now_champ(), end)
    raw_cache = await job_get(session, "event_season")
    cache = raw_cache.get("by_uid") or {} if _season_cache_ok(raw_cache, start, end) else {}
    parts = (await session.execute(select(Participant))).scalars().all()
    uids = [p.uid for p in parts]
    opens = await _snaps_at_or_before(session, uids, start)
    closes = await _snaps_at_or_before(session, uids, through)
    firsts = await _first_snap_between(session, uids, start, through)
    traders = {}
    if parts:
        traders = {
            t.uid: t
            for t in (
                await session.execute(
                    select(Trader).where(Trader.uid.in_(uids))
                )
            ).scalars()
        }
    min_dep = min_event_deposit(cfg)
    day = champ_today()
    ledgers = {}
    if uids:
        ledgers = {
            led.uid: led
            for led in (
                await session.execute(
                    select(DayLedger).where(DayLedger.day == day, DayLedger.uid.in_(uids))
                )
            ).scalars()
        }
    entries = []
    for p in parts:
        close = closes.get(p.uid)
        first = firsts.get(p.uid)
        opening = opens.get(p.uid)
        trader = traders.get(p.uid)
        led = ledgers.get(p.uid)
        stats_dep = float(cache.get(str(p.uid)) or cache.get(p.uid) or 0)
        snap_dep = season_deposit_delta(
            float(opening.sum_deposits) if opening else None,
            float(first.sum_deposits) if first else None,
            float(close.sum_deposits) if close else None,
        )
        dep = stats_dep if snap_dep is None else max(stats_dep, snap_dep)
        # Partners API does not provide a reliable turnover value for this contest.
        turn = 0.0
        pnl = float(led.contest_pnl) if led else 0.0
        trading = float(led.trading_pnl) if led else 0.0
        balance = float(led.last_balance) if led else (float(close.balance) if close else 0.0)
        ret = float(led.return_pct) if led else 0.0
        trading_ret = float(return_pct(led.trading_pnl, led.basis)) if led else 0.0
        status = (led.status or "").strip().lower() if led else ""
        blocked = bool(led and (led.self_excluded or (status and status != "active")))
        entries.append(
            {
                "uid": p.uid,
                "name": p.nickname or "Трейдер",
                "dep": dep,
                "turn": turn,
                "balance": balance,
                "pnl": pnl,
                "trading_pnl": trading,
                "return_pct": ret,
                "trading_return_pct": trading_ret,
                "blocked": blocked,
                "dummy": False,
                "in_ranking": dep >= min_dep and not blocked,
            }
        )
    return entries


async def ranked_boards(session: AsyncSession) -> tuple[list[dict], list[dict]]:
    from app.models import RealLeadOverride

    cfg = await get_settings(session)
    threshold = min_event_deposit(cfg)
    reals = await real_entries(session)
    overrides = (await session.execute(select(RealLeadOverride))).scalars().all()
    by_board = {"A": {}, "B": {}}
    for row in overrides:
        if row.board in by_board:
            by_board[row.board][row.uid] = row
    show_a = await list_showcase(session, "A")
    show_b = await list_showcase(session, "B")

    def build(board: str, showcase: list[dict]) -> list[dict]:
        configured = by_board[board]
        entries = []
        for real in reals:
            override = configured.get(real["uid"])
            copy = dict(real)
            if override and override.pinned_place is not None:
                copy["force_nomination"] = True
            if override and override.frozen:
                copy.update(override.values or {})
                if board == "B":
                    copy["trading_pnl"] = copy["pnl"]
                    copy["trading_return_pct"] = copy["return_pct"]
                copy["in_ranking"] = copy["dep"] >= threshold and not copy.get("blocked")
            if copy.get("in_ranking"):
                entries.append(copy)
        ranked = merge_nomination(showcase, entries, board)
        pins = {
            uid: override.pinned_place
            for uid, override in configured.items()
            if override.pinned_place is not None
        }
        return place_pinned(ranked, pins)

    return build("A", show_a), build("B", show_b)


def _sync_dummy_result(row: ShowcaseLead, pnl: float) -> None:
    row.pnl = money(pnl)
    row.balance = money(max(0.0, float(row.dep) + pnl))
    dep = float(row.dep) or 1.0
    row.return_pct = money((pnl / dep) * 100)


async def tick_showcase(session: AsyncSession, rng: random.Random | None = None) -> int:
    await ensure_showcase(session)
    rng = rng or random.Random()
    rows = (
        await session.execute(select(ShowcaseLead).order_by(ShowcaseLead.board, ShowcaseLead.place))
    ).scalars().all()
    taken: dict[str, set[str]] = {"A": set(), "B": set()}
    for row in rows:
        taken[board_code(getattr(row, "board", "A"))].add(row.name)
    changed = 0
    for row in rows:
        if row.hidden or not bool(getattr(row, "randomize", True)):
            continue
        code = board_code(getattr(row, "board", "A"))
        names = taken[code]
        mutated = False
        if rng.random() < 0.6:
            row.dep = money(nudge_amount(float(row.dep), rng))
            mutated = True
        if rng.random() < 0.5:
            current = abs(float(getattr(row, "pnl", 0) or 800))
            magnitude = nudge_amount(max(50.0, current), rng, lo=50, hi=80_000)
            pnl = -magnitude if code == "B" else magnitude
            _sync_dummy_result(row, pnl)
            mutated = True
        elif mutated:
            _sync_dummy_result(row, float(getattr(row, "pnl", 0) or 0))
        if rng.random() < 0.04:
            names.discard(row.name)
            row.name = pick_dummy_name(row.name, names, rng)
            names.add(row.name)
            mutated = True
        if mutated:
            changed += 1
    if changed:
        await session.commit()
    return changed


def _slim_board(board: list[dict]) -> list[dict]:
    return [
        {
            "uid": r["uid"],
            "name": r["name"],
            "dep": r["dep"],
            "pnl": r.get("pnl") or 0,
            "return_pct": r.get("return_pct") or 0,
            "rank": r["rank"],
            "dummy": bool(r.get("dummy")),
        }
        for r in board[:80]
    ]


def _scope_events(events: list[dict], board: str) -> list[dict]:
    scope = "B" if board_code(board) == "B" else "A"
    return [{**ev, "scope": scope} for ev in events]


def _rank_rows(board: list[dict]) -> list[dict]:
    return [
        {
            "uid": r["uid"],
            "name": r["name"],
            "dep": r.get("dep") or 0,
            "balance": r.get("balance") or 0,
            "pnl": r.get("pnl") or 0,
            "return_pct": r.get("return_pct") or 0,
            "rank": r["rank"],
            "dummy": bool(r.get("dummy")),
        }
        for r in board
    ]


async def _lock_event(session: AsyncSession) -> None:
    conn = await session.connection()
    if conn.dialect.name != "postgresql":
        return
    await session.execute(text("SELECT pg_advisory_xact_lock(814201)"))


async def refresh_event_boards(session: AsyncSession) -> tuple[list[dict], list[dict], list[dict]]:
    board_a, board_b = await ranked_boards(session)
    await _lock_event(session)
    session.expire_all()
    state = await job_get(session, "event_live")
    fresh = "board_a" not in state
    old_a = state.get("board_a") or ([] if fresh else state.get("board") or [])
    old_b = state.get("board_b") or []
    events: list[dict] = []
    if not fresh:
        events.extend(_scope_events(overtake_events(old_a, board_a) + dummy_live_events(old_a, board_a), "A"))
        events.extend(_scope_events(overtake_events(old_b, board_b) + dummy_live_events(old_b, board_b), "B"))
    now = now_champ().timestamp()
    live = list(state.get("activity") or [])
    for ev in reversed(events):
        live.insert(0, {**ev, "ts": now})
    live = live[:20]
    await job_set(
        session,
        "event_live",
        {
            "board_a": _slim_board(board_a),
            "board_b": _slim_board(board_b),
            "ranks_a": _rank_rows(board_a),
            "ranks_b": _rank_rows(board_b),
            "activity": live,
        },
    )
    return board_a, board_b, live


async def refresh_event_board(session: AsyncSession) -> tuple[list[dict], list[dict]]:
    board_a, _board_b, live = await refresh_event_boards(session)
    return board_a, live


def _public_top(board: list[dict], limit: int = 10) -> list[dict]:
    out = []
    for r in board:
        if int(r["rank"]) > limit:
            break
        pnl = float(r.get("pnl") or 0)
        out.append(
            {
                "place": r["rank"],
                "name": r["name"],
                "dep": r["dep"],
                "balance": r.get("balance") or 0,
                "pnl": pnl,
                "loss": max(0.0, -pnl),
                "return_pct": r.get("return_pct") or 0,
                "dummy": bool(r.get("dummy")),
            }
        )
    return out


def _format_activity(live: list[dict], now: float) -> list[dict]:
    out = []
    for row in live:
        name = str(row.get("name") or "").strip()
        action = str(row.get("action") or "").strip()
        if not name or not action:
            continue
        scope = row.get("scope") if row.get("scope") in ("A", "B") else ""
        # Place must not sit inside «пополнил депозит на $…».
        rank = None if action == "пополнил депозит на" else row.get("rank")
        out.append(
            {
                "name": name,
                "action": action,
                "extra": row.get("extra") or "",
                "rank": rank,
                "scope": scope,
                "time": activity_time_label(float(row.get("ts") or now), now),
            }
        )
        if len(out) >= 6:
            break
    return out


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
                "uid": 0,
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
        "balance": me.get("balance") or 0,
        "pnl": me.get("pnl") or 0,
        "return_pct": me.get("return_pct") or 0,
        "beaten": beaten,
        "total": total,
        "neighbors": neighbors,
        "in_ranking": True,
        "need_deposit": 0.0,
    }


def _unranked_profile(
    uid: int,
    name: str,
    dep: float,
    min_dep: float,
    total: int,
    balance: float = 0.0,
    pnl: float = 0.0,
    return_pct: float = 0.0,
) -> dict:
    return {
        "uid": uid,
        "name": name,
        "rank": 0,
        "dep": dep,
        "balance": balance,
        "pnl": pnl,
        "return_pct": return_pct,
        "beaten": 0,
        "total": max(1, total),
        "neighbors": [],
        "in_ranking": False,
        "need_deposit": max(0.0, min_dep - dep),
        "ranking_reason": "need_deposit" if dep < min_dep else "waiting_result",
        "rank_a": 0,
        "rank_b": 0,
    }


def _dual_profile(
    board_a: list[dict],
    board_b: list[dict],
    uid: int,
    stats_players: int | None = None,
) -> dict | None:
    left = _profile_payload(board_a, uid, stats_players)
    right = _profile_payload(board_b, uid, stats_players)
    if left is None and right is None:
        return None
    base = dict(left or right or {})
    base["rank_a"] = int(left["rank"]) if left else 0
    base["rank_b"] = int(right["rank"]) if right else 0
    base["rank"] = base["rank_a"] or base["rank_b"]
    base["in_ranking"] = True
    if left:
        base["neighbors"] = left["neighbors"]
    return base


async def lookup_event_uid(session: AsyncSession, uid: int) -> dict:
    if uid < 100_000_000 or uid > 9_999_999_999:
        raise HTTPException(400, "format")
    try:
        info = await partners_client.user_info(uid)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Проверка UID временно недоступна") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Проверка UID временно недоступна") from exc
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
        log.exception("event snapshot failed uid=%s", uid)
        await session.rollback()
    cfg = await get_settings(session)
    min_dep = min_event_deposit(cfg)
    board_a, board_b, _live = await refresh_event_boards(session)
    profile = _dual_profile(board_a, board_b, uid)
    if profile:
        return {
            "uid": uid,
            "status": "ok",
            "min_deposit": min_dep,
            "need_deposit": 0.0,
            "you": profile,
        }
    me = next((r for r in await real_entries(session) if int(r["uid"]) == int(uid)), None)
    if me is None:
        return {"uid": uid, "status": "need_name"}
    you = _unranked_profile(
        uid,
        me["name"],
        float(me["dep"]),
        min_dep,
        len(board_a),
        float(me.get("balance") or 0),
        float(me.get("pnl") or 0),
        float(me.get("return_pct") or 0),
    )
    return {
        "uid": uid,
        "status": "need_deposit" if you["need_deposit"] > 0 else "waiting_result",
        "min_deposit": min_dep,
        "need_deposit": you["need_deposit"],
        "you": you,
    }


async def register_event_name(
    session: AsyncSession, uid: int, nickname: str, telegram: str = ""
) -> dict:
    check = await lookup_event_uid(session, uid)
    if check["status"] == "not_in_base":
        raise HTTPException(status_code=404, detail="not_in_base")
    if check["status"] == "ok" and check.get("you"):
        return check

    nick = nickname.strip()[:64]
    tg = str(telegram or "").strip().lstrip("@")[:64]
    part = (
        await session.execute(select(Participant).where(Participant.uid == uid))
    ).scalar_one_or_none()
    # A public repeat must not rewrite a name or contact that is already saved.
    if part is not None and (part.nickname or "").strip():
        nick = part.nickname
    else:
        try:
            info = await partners_client.user_info(uid)
        except (httpx.HTTPError, RuntimeError):
            info = None
        if part is None:
            part = Participant(
                uid=uid,
                nickname=nick,
                telegram=tg,
                country=(info or {}).get("country") if isinstance(info, dict) else None,
            )
            session.add(part)
        else:
            part.nickname = nick
            if tg and not (part.telegram or "").strip():
                part.telegram = tg
        await session.commit()

    try:
        from app.services.poll import snapshot_uid

        await snapshot_uid(session, uid)
    except Exception:
        log.exception("event snapshot failed uid=%s", uid)
        await session.rollback()

    cfg = await get_settings(session)
    min_dep = min_event_deposit(cfg)
    board_a, board_b, _live = await refresh_event_boards(session)
    profile = _dual_profile(board_a, board_b, uid)
    if profile is None:
        me = next((r for r in await real_entries(session) if int(r["uid"]) == int(uid)), None)
        dep = float(me["dep"]) if me else 0.0
        profile = _unranked_profile(
            uid,
            nick,
            dep,
            min_dep,
            len(board_a),
            float(me.get("balance") or 0) if me else 0.0,
            float(me.get("pnl") or 0) if me else 0.0,
            float(me.get("return_pct") or 0) if me else 0.0,
        )
        return {
            "uid": uid,
            "status": "need_deposit" if profile["need_deposit"] > 0 else "waiting_result",
            "min_deposit": min_dep,
            "need_deposit": profile["need_deposit"],
            "you": profile,
        }
    return {
        "uid": uid,
        "status": "ok",
        "min_deposit": min_dep,
        "need_deposit": 0.0,
        "you": profile,
    }


async def invite_preview(session: AsyncSession, uid: int) -> dict:
    part = (
        await session.execute(select(Participant).where(Participant.uid == uid))
    ).scalar_one_or_none()
    if not part or not (part.nickname or "").strip():
        raise HTTPException(404, "not found")
    board_a, board_b, _live = await refresh_event_boards(session)
    profile = _dual_profile(board_a, board_b, uid)
    if not profile:
        raise HTTPException(404, "not found")
    return {
        "uid": uid,
        "name": profile["name"],
        "rank": profile["rank"],
        "dep": profile["dep"],
    }
