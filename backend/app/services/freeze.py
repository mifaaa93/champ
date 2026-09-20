from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ledger import money
from app.models import DayLedger, DayResult, Participant
from app.services.ranking import RankRow, pick_winners
from app.settings_service import get_settings
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
                return_pct=led.return_pct,
                day_deposits=led.day_deposits,
                day_withdrawals=led.day_withdrawals,
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
    if existing:
        return {"status": "already_frozen", "day": str(day), "count": len(existing)}

    cfg = await get_settings(session)
    rows = await load_rank_rows(session, day)
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
                )
            )
            count += 1
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
    return {"status": "frozen", "day": str(day), "count": count, "winners": safe}
