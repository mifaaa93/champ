from decimal import Decimal

from app.ledger import (
    MoneyPoint,
    basis,
    contest_pnl,
    loss_compensation,
    return_pct,
    trading_pnl,
)


def P(bal, dep=0, wdr=0, bon=0) -> MoneyPoint:
    return MoneyPoint(
        balance=Decimal(str(bal)),
        sum_deposits=Decimal(str(dep)),
        sum_withdrawals=Decimal(str(wdr)),
        sum_bonuses=Decimal(str(bon)),
    )


def test_pure_trading_gain():
    start, now = P(400), P(1000)
    assert contest_pnl(start, now) == Decimal("600")
    assert return_pct(Decimal("600"), Decimal("400")) == Decimal("150")


def test_deposit_is_not_profit():
    start, now = P(100, dep=100), P(200, dep=200)
    assert contest_pnl(start, now) == Decimal("0")


def test_bonus_is_not_profit():
    start, now = P(50, bon=0), P(150, bon=100)
    assert contest_pnl(start, now) == Decimal("0")


def test_withdrawal_drops_score():
    start, now = P(500, wdr=0), P(400, wdr=100)
    assert contest_pnl(start, now) == Decimal("-100")
    assert trading_pnl(start, now) == Decimal("0")


def test_zero_start_uses_deposit_as_basis():
    start, now = P(0, dep=0), P(80, dep=50)
    assert basis(start, now) == Decimal("50")
    assert contest_pnl(start, now) == Decimal("30")


def test_loss_comp_cap():
    pnl = Decimal("-10000")
    assert loss_compensation(pnl, Decimal("15"), Decimal("500")) == Decimal("500")
    assert loss_compensation(pnl, Decimal("15"), Decimal("0")) == Decimal("1500")
    assert loss_compensation(Decimal("10"), Decimal("15"), Decimal("500")) == Decimal("0")
