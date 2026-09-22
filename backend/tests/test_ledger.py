from decimal import Decimal

from app.ledger import (
    MoneyPoint,
    SnapRef,
    basis,
    contest_pnl,
    loss_compensation,
    pick_start_snapshot,
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


def test_t0_after_deposit_not_leftover():
    leftover = SnapRef(1, Decimal("1034"), Decimal("1.27"))
    after = SnapRef(2, Decimal("1084"), Decimal("51.27"))
    picked = pick_start_snapshot([leftover, after], Decimal("50"), Decimal("50"))
    assert picked is not None
    assert picked.id == 2
    assert picked.balance == Decimal("51.27")


def test_t0_first_snap_if_deposit_already_inside():
    first = SnapRef(1, Decimal("500"), Decimal("520"))
    later = SnapRef(2, Decimal("500"), Decimal("510"))
    picked = pick_start_snapshot([first, later], Decimal("50"), Decimal("80"))
    assert picked is not None
    assert picked.id == 1


def test_t0_none_without_qualifying_deposit():
    only = SnapRef(1, Decimal("100"), Decimal("1.27"))
    assert pick_start_snapshot([only], Decimal("50"), Decimal("0")) is None


def test_loss_comp_cap():
    pnl = Decimal("-10000")
    assert loss_compensation(pnl, Decimal("15"), Decimal("500")) == Decimal("500")
    assert loss_compensation(pnl, Decimal("15"), Decimal("0")) == Decimal("1500")
    assert loss_compensation(Decimal("10"), Decimal("15"), Decimal("500")) == Decimal("0")
