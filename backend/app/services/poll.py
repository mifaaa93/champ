from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ledger import (
    MoneyPoint,
    basis,
    contest_pnl,
    delta_bonuses,
    delta_deposits,
    delta_withdrawals,
    money,
    return_pct,
    trading_pnl,
)
from app.models import DayLedger, Participant, Snapshot, Trader
from app.partners import partners_client
from app.settings_service import get_settings
from app.timezone import dubai_today, now_utc

log = logging.getLogger("champ.poll")

RECONCILE_THRESHOLD = Decimal("1")


def _point_from_info(info: dict) -> MoneyPoint:
    return MoneyPoint(
        balance=money(info.get("balance")),
        sum_deposits=money(info.get("sum_deposits")),
        sum_withdrawals=money(info.get("sum_withdrawals")),
        sum_bonuses=money(info.get("sum_bonuses")),
    )


async def refresh_statistics(session: AsyncSession, day: date | None = None) -> dict:
    day = day or dubai_today()
    payload = await partners_client.statistics_traders(day.isoformat())
    if payload.get("truncated"):
        log.error("statistics truncated for %s", day)
    rows = payload.get("data") or []
    by_uid: dict[int, dict] = {}
    for row in rows:
        try:
            uid = int(row.get("group1"))
        except (TypeError, ValueError):
            continue
        by_uid[uid] = row

    cfg = await get_settings(session)
    min_dep = money(cfg["min_day_deposit"])
    participants = {
        p.uid: p for p in (await session.execute(select(Participant))).scalars()
    }

    for uid, part in participants.items():
        stats = by_uid.get(uid, {})
        depo = money(stats.get("depo_sum"))
        wdrw = money(stats.get("wdrw_sum"))
        trades = int(stats.get("count_trades") or 0)
        led = (
            await session.execute(
                select(DayLedger).where(DayLedger.day == day, DayLedger.uid == uid)
            )
        ).scalar_one_or_none()
        if led is None:
            led = DayLedger(day=day, uid=uid, registered=True)
            session.add(led)
        led.registered = True
        led.stats_depo_sum = depo
        led.stats_wdrw_sum = wdrw
        led.stats_trades = trades
        _recompute_eligibility(led, min_dep, bool(cfg["require_trade"]))

    await session.commit()
    return {
        "day": str(day),
        "stats_rows": len(rows),
        "participants": len(participants),
        "truncated": bool(payload.get("truncated")),
    }


async def snapshot_uid(session: AsyncSession, uid: int, day: date | None = None) -> Snapshot | None:
    day = day or dubai_today()
    info = await partners_client.user_info(uid)
    if not info:
        log.warning("user-info missing for %s", uid)
        return None

    trader = await session.get(Trader, uid)
    if trader is None:
        trader = Trader(uid=uid)
        session.add(trader)
    trader.status = str(info.get("status") or "")
    trader.self_excluded = bool(info.get("self_excluded"))
    trader.is_verified = bool(info.get("is_verified"))
    trader.country = info.get("country")
    trader.last_user_info = info

    ts = now_utc()
    snap = Snapshot(
        uid=uid,
        ts=ts,
        day=day,
        balance=money(info.get("balance")),
        sum_deposits=money(info.get("sum_deposits")),
        sum_withdrawals=money(info.get("sum_withdrawals")),
        sum_bonuses=money(info.get("sum_bonuses")),
        count_deposits=int(info.get("count_deposits") or 0),
        status=str(info.get("status") or ""),
        self_excluded=bool(info.get("self_excluded")),
        raw=info,
    )
    session.add(snap)
    await session.flush()

    led = (
        await session.execute(
            select(DayLedger).where(DayLedger.day == day, DayLedger.uid == uid)
        )
    ).scalar_one_or_none()
    if led is None:
        led = DayLedger(day=day, uid=uid, registered=True)
        session.add(led)
        await session.flush()

    if led.start_snapshot_id is None:
        led.start_snapshot_id = snap.id
        led.start_balance = snap.balance

    start_snap = await session.get(Snapshot, led.start_snapshot_id)
    if start_snap is None:
        start_snap = snap
        led.start_snapshot_id = snap.id
        led.start_balance = snap.balance

    start = MoneyPoint(
        balance=start_snap.balance,
        sum_deposits=start_snap.sum_deposits,
        sum_withdrawals=start_snap.sum_withdrawals,
        sum_bonuses=start_snap.sum_bonuses,
    )
    now = _point_from_info(info)
    led.last_snapshot_id = snap.id
    led.last_balance = now.balance
    led.status = snap.status
    led.self_excluded = snap.self_excluded
    led.day_deposits = delta_deposits(start, now)
    led.day_withdrawals = delta_withdrawals(start, now)
    led.day_bonuses = delta_bonuses(start, now)
    led.contest_pnl = contest_pnl(start, now)
    led.trading_pnl = trading_pnl(start, now)
    led.basis = basis(start, now)
    led.return_pct = return_pct(led.contest_pnl, led.basis)
    led.registered = True
    if abs(led.day_deposits - led.stats_depo_sum) > RECONCILE_THRESHOLD and led.stats_depo_sum > 0:
        led.reconcile_flag = True
    else:
        led.reconcile_flag = False

    cfg = await get_settings(session)
    _recompute_eligibility(led, money(cfg["min_day_deposit"]), bool(cfg["require_trade"]))
    await session.commit()
    return snap


def _recompute_eligibility(led: DayLedger, min_dep: Decimal, require_trade: bool) -> None:
    reasons: list[str] = []
    if not led.registered:
        reasons.append("not_registered")
    deposited = max(led.stats_depo_sum or 0, led.day_deposits or 0)
    if deposited < min_dep:
        reasons.append("min_deposit")
    if require_trade and led.stats_trades < 1:
        reasons.append("no_trades")
    if led.start_snapshot_id is None:
        reasons.append("no_start")
    elif (led.status or "").lower() != "active":
        reasons.append("inactive")
    if led.self_excluded:
        reasons.append("self_excluded")
    if led.basis is not None and led.basis <= 0:
        reasons.append("no_basis")
    led.eligible = len(reasons) == 0
    led.dq_reason = ",".join(reasons)


async def snapshot_watchlist(session: AsyncSession) -> dict:
    day = dubai_today()
    cfg = await get_settings(session)
    uids = [p.uid for p in (await session.execute(select(Participant))).scalars()]
    ok = 0
    fail = 0
    for uid in uids:
        try:
            snap = await snapshot_uid(session, uid, day)
            if snap:
                ok += 1
            else:
                fail += 1
        except Exception:
            log.exception("snapshot failed uid=%s", uid)
            fail += 1
    return {"day": str(day), "ok": ok, "fail": fail, "interval_hint": max(5, (len(uids) + 29) // 30)}
