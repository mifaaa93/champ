from dataclasses import dataclass
from decimal import Decimal

from app.ledger import ZERO, loss_compensation, money


@dataclass
class RankRow:
    uid: int
    nickname: str
    last_balance: Decimal
    contest_pnl: Decimal
    trading_pnl: Decimal
    return_pct: Decimal
    trading_return_pct: Decimal
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
    return sorted(rows, key=lambda r: (r.trading_pnl, r.trading_return_pct, r.uid))


def eligible_only(rows: list[RankRow]) -> list[RankRow]:
    return [r for r in rows if r.eligible]


def yield_pool(rows: list[RankRow]) -> list[RankRow]:
    return sort_yield([r for r in eligible_only(rows) if r.contest_pnl > ZERO])


def loss_pool(rows: list[RankRow]) -> list[RankRow]:
    return sort_loss([r for r in eligible_only(rows) if r.trading_pnl < ZERO])


EPS_MONEY = Decimal("0.01")
EPS_PCT = Decimal("0.01")


def _place(pool: list[RankRow], uid: int) -> int | None:
    for i, row in enumerate(pool, 1):
        if row.uid == uid:
            return i
    return None


def _at(pool: list[RankRow], place: int) -> RankRow | None:
    if place < 1 or place > len(pool):
        return None
    return pool[place - 1]


def yield_target(me: RankRow | None, pool: list[RankRow], place: int) -> dict:
    """Extra contest PnL / % to reach `place` in yield (must beat the occupant)."""
    occupied = len(pool)
    my_place = _place(pool, me.uid) if me else None
    if my_place is not None and my_place <= place:
        return {
            "already": True,
            "place": my_place,
            "need_pnl": 0.0,
            "need_pct": 0.0,
            "target_pct": float(me.return_pct) if me else 0.0,
            "open_slot": False,
            "occupied": occupied,
        }
    rival = _at(pool, place)
    if rival is None:
        if me and me.contest_pnl > ZERO:
            return {
                "already": True,
                "place": my_place,
                "need_pnl": 0.0,
                "need_pct": 0.0,
                "target_pct": float(me.return_pct),
                "open_slot": True,
                "occupied": occupied,
            }
        recover = float(-me.contest_pnl + EPS_MONEY) if me else float(EPS_MONEY)
        return {
            "already": False,
            "place": my_place,
            "need_pnl": recover,
            "need_pct": None,
            "target_pct": None,
            "open_slot": True,
            "occupied": occupied,
        }
    target_pct = rival.return_pct + EPS_PCT
    base = me.basis if me and me.basis > ZERO else ZERO
    if me is None or base <= ZERO:
        return {
            "already": False,
            "place": my_place,
            "need_pnl": None,
            "need_pct": float(target_pct),
            "target_pct": float(target_pct),
            "open_slot": False,
            "occupied": occupied,
        }
    target_pnl = (target_pct / Decimal("100")) * base
    need_pnl = target_pnl - me.contest_pnl
    if need_pnl < ZERO:
        need_pnl = ZERO
    need_pct = target_pct - me.return_pct
    if need_pct < ZERO:
        need_pct = ZERO
    return {
        "already": False,
        "place": my_place,
        "need_pnl": float(need_pnl),
        "need_pct": float(need_pct),
        "target_pct": float(target_pct),
        "open_slot": False,
        "occupied": occupied,
    }


def loss_target(me: RankRow | None, pool: list[RankRow], place: int) -> dict:
    occupied = len(pool)
    my_place = _place(pool, me.uid) if me else None
    if my_place is not None and my_place <= place:
        return {
            "already": True,
            "place": my_place,
            "need_pnl": 0.0,
            "target_pnl": float(me.trading_pnl) if me else 0.0,
            "open_slot": False,
            "occupied": occupied,
        }
    rival = _at(pool, place)
    current = me.trading_pnl if me else ZERO
    if rival is None:
        if me and me.trading_pnl < ZERO:
            return {
                "already": True,
                "place": my_place,
                "need_pnl": 0.0,
                "target_pnl": float(me.trading_pnl),
                "open_slot": True,
                "occupied": occupied,
            }
        extra = current + EPS_MONEY if current >= ZERO else ZERO
        return {
            "already": False,
            "place": my_place,
            "need_pnl": float(extra),
            "target_pnl": float(-EPS_MONEY),
            "open_slot": True,
            "occupied": occupied,
        }
    target = rival.trading_pnl - EPS_MONEY
    extra = current - target
    if extra < ZERO:
        extra = ZERO
    return {
        "already": False,
        "place": my_place,
        "need_pnl": float(extra),
        "target_pnl": float(target),
        "open_slot": False,
        "occupied": occupied,
    }


def pick_winners(
    rows: list[RankRow],
    places: int,
    prize_yield: list,
    prize_loss_pct: list,
    loss_cap: Decimal,
) -> dict[str, list[dict]]:
    a = yield_pool(rows)[:places]
    a_uids = {r.uid for r in a}
    b = [r for r in loss_pool(rows) if r.uid not in a_uids][:places]

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
        amount = loss_compensation(row.trading_pnl, pct, loss_cap)
        b_out.append(
            {
                "place": i + 1,
                "uid": row.uid,
                "nickname": row.nickname,
                "metric": row.trading_pnl,
                "pnl": row.trading_pnl,
                "prize_amount": amount,
                "prize_note": f"{pct}% от торговой просадки, кап ${loss_cap}",
            }
        )
    return {"yield": a_out, "loss": b_out}
