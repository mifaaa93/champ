from dataclasses import dataclass
from decimal import Decimal

from app.ledger import ZERO, loss_compensation, money


@dataclass
class RankRow:
    uid: int
    nickname: str
    last_balance: Decimal
    contest_pnl: Decimal
    return_pct: Decimal
    day_deposits: Decimal
    day_withdrawals: Decimal
    day_bonuses: Decimal
    basis: Decimal
    eligible: bool
    dq_reason: str
    snapshot_ts: str | None = None


def sort_yield(rows: list[RankRow]) -> list[RankRow]:
    return sorted(rows, key=lambda r: (r.return_pct, r.contest_pnl, -r.uid), reverse=True)


def sort_loss(rows: list[RankRow]) -> list[RankRow]:
    return sorted(rows, key=lambda r: (r.contest_pnl, r.return_pct, r.uid))


def eligible_only(rows: list[RankRow]) -> list[RankRow]:
    return [r for r in rows if r.eligible]


def pick_winners(
    rows: list[RankRow],
    places: int,
    prize_yield: list,
    prize_loss_pct: list,
    loss_cap: Decimal,
) -> dict[str, list[dict]]:
    live = eligible_only(rows)
    a = sort_yield(live)[:places]
    a_uids = {r.uid for r in a}
    b_pool = [r for r in sort_loss(live) if r.uid not in a_uids and r.contest_pnl < ZERO]
    b = b_pool[:places]

    a_out = []
    for i, row in enumerate(a):
        amount = money(prize_yield[i]) if i < len(prize_yield) else ZERO
        a_out.append(
            {
                "place": i + 1,
                "uid": row.uid,
                "nickname": row.nickname,
                "metric": row.return_pct,
                "pnl": row.contest_pnl,
                "prize_amount": amount,
                "prize_note": f"${amount} за доходность",
            }
        )

    b_out = []
    for i, row in enumerate(b):
        pct = money(prize_loss_pct[i]) if i < len(prize_loss_pct) else ZERO
        amount = loss_compensation(row.contest_pnl, pct, loss_cap)
        b_out.append(
            {
                "place": i + 1,
                "uid": row.uid,
                "nickname": row.nickname,
                "metric": row.contest_pnl,
                "pnl": row.contest_pnl,
                "prize_amount": amount,
                "prize_note": f"{pct}% от просадки, кап ${loss_cap}",
            }
        )
    return {"yield": a_out, "loss": b_out}
