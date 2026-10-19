from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ledger import (
    ZERO,
    MoneyPoint,
    SnapRef,
    basis,
    contest_pnl,
    delta_bonuses,
    delta_withdrawals,
    money,
    pick_start_snapshot,
    return_pct,
    trading_pnl,
)
from app.models import DayLedger, Participant, Snapshot, Trader
from app.partners import partners_client
from app.settings_service import get_settings
from app.timezone import CHAMP_TZ, dubai_today, now_utc

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
    truncated = bool(payload.get("truncated"))
    if truncated:
        log.error("statistics truncated for %s; previous values kept", day)
        return {
            "day": str(day),
            "stats_rows": 0,
            "participants": 0,
            "truncated": True,
            "skipped": True,
        }
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

    # A missing row is not a proven zero: the feed can omit a trader or
    # filter to deposited=1. Only rows that are actually present are written.
    for uid, part in participants.items():
        stats = by_uid.get(uid)
        if stats is None:
            continue
        depo = money(stats.get("depo_sum"))
        wdrw = money(stats.get("wdrw_sum"))
        trades = int(stats.get("count_trades") or 0)
        led = (
            await session.execute(
                select(DayLedger)
                .where(DayLedger.day == day, DayLedger.uid == uid)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if led is None:
            led = DayLedger(day=day, uid=uid, registered=True)
            session.add(led)
        led.registered = True
        led.stats_depo_sum = depo
        led.stats_wdrw_sum = wdrw
        led.stats_trades = trades
        led.updated_at = now_utc()
        _recompute_eligibility(led, min_dep, bool(cfg["require_trade"]))

    await session.commit()
    return {
        "day": str(day),
        "stats_rows": len(rows),
        "participants": len(participants),
        "truncated": False,
        "skipped": False,
    }


async def snapshot_uid(session: AsyncSession, uid: int, day: date | None = None) -> Snapshot | None:
    info = await partners_client.user_info(uid)
    if not info:
        log.warning("user-info missing for %s", uid)
        return None
    # The day is the time of this response, not the time the batch started.
    # A slow poll that crosses midnight must not write today's trades onto yesterday.
    observed = now_utc()
    actual_day = observed.astimezone(CHAMP_TZ).date()
    if day is not None and day != actual_day:
        log.info(
            "snapshot crossed midnight uid=%s requested=%s actual=%s",
            uid,
            day,
            actual_day,
        )
    day = actual_day

    trader = await session.get(Trader, uid)
    if trader is None:
        trader = Trader(uid=uid)
        session.add(trader)
    trader.status = str(info.get("status") or "")
    trader.self_excluded = bool(info.get("self_excluded"))
    trader.is_verified = bool(info.get("is_verified"))
    trader.country = info.get("country")
    trader.last_user_info = info

    ts = observed
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
        select(DayLedger)
        .where(DayLedger.day == day, DayLedger.uid == uid)
        .with_for_update()
        .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if led is None:
        led = DayLedger(day=day, uid=uid, registered=True)
        session.add(led)
        await session.flush()

    cfg = await get_settings(session)
    min_dep = money(cfg["min_day_deposit"])
    day_snaps = list(
        (
            await session.execute(
                select(Snapshot)
                .where(Snapshot.uid == uid, Snapshot.day == day)
                .order_by(Snapshot.ts.asc(), Snapshot.id.asc())
            )
        ).scalars()
    )
    baseline_row = (
        await session.execute(
            select(Snapshot.sum_deposits)
            .where(Snapshot.uid == uid, Snapshot.day < day)
            .order_by(Snapshot.ts.desc(), Snapshot.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    baseline = money(baseline_row) if baseline_row is not None else None
    now = _point_from_info(info)
    opening = day_snaps[0] if day_snaps else snap
    picked = pick_start_snapshot(
        [SnapRef(s.id, s.sum_deposits, s.balance) for s in day_snaps],
        min_dep,
        money(led.stats_depo_sum),
        baseline=baseline,
        locked_id=led.start_snapshot_id,
    )
    if baseline is not None:
        day_total = max(ZERO, now.sum_deposits - baseline)
    else:
        day_total = max(ZERO, now.sum_deposits - opening.sum_deposits)
    led.day_deposits = day_total
    if picked is None:
        led.start_snapshot_id = None
        led.start_balance = ZERO
        led.day_withdrawals = now.sum_withdrawals - opening.sum_withdrawals
        led.day_bonuses = ZERO
        led.contest_pnl = ZERO
        led.trading_pnl = ZERO
        led.basis = ZERO
        led.return_pct = ZERO
    else:
        start_snap = next(s for s in day_snaps if s.id == picked.id)
        led.start_snapshot_id = start_snap.id
        led.start_balance = start_snap.balance
        start = MoneyPoint(
            balance=start_snap.balance,
            sum_deposits=start_snap.sum_deposits,
            sum_withdrawals=start_snap.sum_withdrawals,
            sum_bonuses=start_snap.sum_bonuses,
        )
        led.day_withdrawals = delta_withdrawals(start, now)
        led.day_bonuses = delta_bonuses(start, now)
        led.contest_pnl = contest_pnl(start, now)
        led.trading_pnl = trading_pnl(start, now)
        if baseline is not None:
            included = max(ZERO, start_snap.sum_deposits - baseline)
        else:
            included = max(ZERO, start_snap.sum_deposits - opening.sum_deposits)
        led.basis = basis(start, now, included)
        led.return_pct = return_pct(led.contest_pnl, led.basis)

    led.last_snapshot_id = snap.id
    led.last_balance = now.balance
    led.status = snap.status
    led.self_excluded = snap.self_excluded
    member = (
        await session.execute(select(Participant.uid).where(Participant.uid == uid))
    ).scalar_one_or_none()
    led.registered = member is not None
    led.updated_at = observed
    stats_depo = money(led.stats_depo_sum)
    if stats_depo > 0 and abs(day_total - stats_depo) > RECONCILE_THRESHOLD:
        led.reconcile_flag = True
    else:
        led.reconcile_flag = False

    _recompute_eligibility(led, min_dep, bool(cfg["require_trade"]))
    await session.commit()
    return snap


def _recompute_eligibility(led: DayLedger, min_dep: Decimal, require_trade: bool) -> None:
    reasons: list[str] = []
    if not led.registered:
        reasons.append("not_registered")
    deposited = max(led.stats_depo_sum or 0, led.day_deposits or 0)
    # A locked start already proved the buy-in. A late statistics row must not
    # kick the trader out, and deposits after t0 are not the qualifying sum.
    if led.start_snapshot_id is not None:
        deposited = max(deposited, min_dep)
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
            await session.rollback()
            fail += 1
    return {"day": str(day), "ok": ok, "fail": fail, "interval_hint": max(5, (len(uids) + 29) // 30)}
