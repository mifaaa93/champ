from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ledger import money, return_pct
from app.schemas import day_cash
from app.models import DayLedger, DayResult, Participant
from app.services.ranking import RankRow, pick_winners
from app.settings_service import get_settings, job_get, job_set
from app.timezone import now_utc


async def load_rank_rows(session: AsyncSession, day) -> list[RankRow]:
    q = await session.execute(select(DayLedger).where(DayLedger.day == day))
    ledgers = list(q.scalars())
    parts = {
        p.uid: p
        for p in (await session.execute(select(Participant))).scalars()
    }
    rows: list[RankRow] = []
    for led in ledgers:
        p = parts.get(led.uid)
        rows.append(
            RankRow(
                uid=led.uid,
                nickname=(p.nickname if p and p.nickname else ""),
                last_balance=led.last_balance,
                contest_pnl=led.contest_pnl,
                trading_pnl=led.trading_pnl,
                return_pct=led.return_pct,
                trading_return_pct=return_pct(led.trading_pnl, led.basis),
                day_deposits=day_cash(led.day_deposits, led.stats_depo_sum),
                day_withdrawals=day_cash(led.day_withdrawals, led.stats_wdrw_sum),
                day_bonuses=led.day_bonuses,
                basis=led.basis,
                eligible=led.eligible,
                dq_reason=led.dq_reason,
            )
        )
    return rows


async def freeze_day(session: AsyncSession, day) -> dict:
    existing = (
        await session.execute(select(DayResult).where(DayResult.day == day))
    ).scalars().all()
    replaced = bool(existing)
    for row in existing:
        await session.delete(row)
    await session.flush()

    cfg = await get_settings(session)
    rows = await load_rank_rows(session, day)
    parts = {
        p.uid: p
        for p in (await session.execute(select(Participant))).scalars()
    }
    ledgers = {
        led.uid: led
        for led in (
            await session.execute(select(DayLedger).where(DayLedger.day == day))
        ).scalars()
    }
    winners = pick_winners(
        rows,
        int(cfg["prize_places"]),
        list(cfg["prize_yield"]),
        list(cfg["prize_loss_pct"]),
        money(cfg["loss_comp_cap"]),
    )
    frozen_at = now_utc()
    count = 0
    for nomination, items in winners.items():
        for item in items:
            part = parts.get(item["uid"])
            led = ledgers.get(item["uid"])
            card = {
                "nickname": (part.nickname if part and part.nickname else "") or item.get("nickname") or "",
                "telegram": (part.telegram if part else "") or "",
                "country": (part.country if part else "") or "",
                "balance": float(led.last_balance) if led else None,
                "start_balance": float(led.start_balance) if led else None,
                "deposits": float(day_cash(led.day_deposits, led.stats_depo_sum)) if led else None,
                "withdrawals": float(day_cash(led.day_withdrawals, led.stats_wdrw_sum)) if led else None,
                "bonuses": float(led.day_bonuses) if led else None,
                "return_pct": float(led.return_pct) if led else None,
                "trading_pnl": float(led.trading_pnl) if led else None,
                "trading_return_pct": float(return_pct(led.trading_pnl, led.basis)) if led else None,
                "trades": int(led.stats_trades) if led else None,
            }
            session.add(
                DayResult(
                    day=day,
                    nomination=nomination,
                    place=item["place"],
                    uid=item["uid"],
                    metric=item["metric"],
                    pnl=item["pnl"],
                    prize_amount=item["prize_amount"],
                    prize_note=item["prize_note"],
                    frozen_at=frozen_at,
                    card=card,
                )
            )
            count += 1
    if count == 0:
        marker = await job_get(session, "day_closed")
        days = set(marker.get("days") or [])
        days.add(str(day))
        await job_set(session, "day_closed", {"days": sorted(days)})
    await session.commit()
    safe = {
        nom: [
            {
                **item,
                "metric": float(item["metric"]),
                "pnl": float(item["pnl"]),
                "prize_amount": float(item["prize_amount"]),
            }
            for item in items
        ]
        for nom, items in winners.items()
    }
    return {
        "status": "refrozen" if replaced else "frozen",
        "day": str(day),
        "count": count,
        "winners": safe,
    }
