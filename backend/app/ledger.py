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


def basis(start: MoneyPoint, now: MoneyPoint) -> Decimal:
    if start.balance > ZERO:
        return start.balance
    deposited = delta_deposits(start, now)
    if deposited > ZERO:
        return deposited
    return MIN_BASIS


def return_pct(pnl: Decimal, base: Decimal) -> Decimal:
    safe = base if base > ZERO else MIN_BASIS
    return (pnl / safe) * Decimal("100")


def loss_compensation(pnl: Decimal, percent: Decimal, cap: Decimal) -> Decimal:
    if pnl >= ZERO:
        return ZERO
    raw = (-pnl) * percent / Decimal("100")
    if cap <= ZERO:
        return raw
    return min(cap, raw)
