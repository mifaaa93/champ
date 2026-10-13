from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0")
MIN_BASIS = Decimal("0.01")


def money(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return ZERO
    if isinstance(value, str):
        return Decimal(value.replace(",", ".").replace(" ", ""))
    return Decimal(str(value))


@dataclass(frozen=True)
class SnapRef:
    id: int
    sum_deposits: Decimal
    balance: Decimal


def pick_start_snapshot(
    snaps: list[SnapRef],
    min_dep: Decimal,
    stats_depo: Decimal = ZERO,
    *,
    baseline: Decimal | None = None,
    locked_id: int | None = None,
) -> SnapRef | None:
    """First snapshot that already includes today's qualifying deposit.

    `stats_depo` is not proof that the buy-in was inside the first snapshot:
    the day total can include money that arrived later. A pre-day `baseline`
    (lifetime deposits before today) is. Once a start id is locked, later
    deposits do not move it. If the moment cannot be shown, return None.
    """
    del stats_depo
    if not snaps:
        return None
    if locked_id is not None:
        locked = next((snap for snap in snaps if snap.id == locked_id), None)
        if locked is not None:
            return locked
    base = snaps[0].sum_deposits if baseline is None else baseline
    for snap in snaps:
        if snap.sum_deposits - base >= min_dep:
            return snap
    return None


@dataclass(frozen=True)
class MoneyPoint:
    balance: Decimal
    sum_deposits: Decimal
    sum_withdrawals: Decimal
    sum_bonuses: Decimal


def contest_pnl(start: MoneyPoint, now: MoneyPoint) -> Decimal:
    """Score used in the ranking.

    Deposits and bonuses are stripped so they are not profit.
    Withdrawals are NOT added back: cashing out drops the score, so
    contestants are incentivized to wait until the day ends.
    """
    return (
        (now.balance - start.balance)
        - (now.sum_deposits - start.sum_deposits)
        - (now.sum_bonuses - start.sum_bonuses)
    )


def trading_pnl(start: MoneyPoint, now: MoneyPoint) -> Decimal:
    """Isolated trading PnL (withdrawals added back). Stored for analytics."""
    return contest_pnl(start, now) + (now.sum_withdrawals - start.sum_withdrawals)


def delta_deposits(start: MoneyPoint, now: MoneyPoint) -> Decimal:
    return now.sum_deposits - start.sum_deposits


def delta_withdrawals(start: MoneyPoint, now: MoneyPoint) -> Decimal:
    return now.sum_withdrawals - start.sum_withdrawals


def delta_bonuses(start: MoneyPoint, now: MoneyPoint) -> Decimal:
    return now.sum_bonuses - start.sum_bonuses


def basis(start: MoneyPoint, now: MoneyPoint, included: Decimal = ZERO) -> Decimal:
    """Capital the percent is measured against.

    Prefer the balance at t0. If that balance is still zero, use deposits
    after t0, then the buy-in already inside the start snapshot. Never invent
    a one-cent base: an unknown base stays zero and the row is not ranked.
    """
    if start.balance > ZERO:
        return start.balance
    deposited = delta_deposits(start, now)
    if deposited > ZERO:
        return deposited
    if included > ZERO:
        return included
    return ZERO


def return_pct(pnl: Decimal, base: Decimal) -> Decimal:
    if base <= ZERO:
        return ZERO
    return (pnl / base) * Decimal("100")


def loss_compensation(pnl: Decimal, percent: Decimal, cap: Decimal) -> Decimal:
    if pnl >= ZERO:
        return ZERO
    raw = (-pnl) * percent / Decimal("100")
    if cap <= ZERO:
        return raw
    return min(cap, raw)
