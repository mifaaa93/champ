from decimal import Decimal

from app.services.ranking import RankRow, pick_winners, sort_loss, sort_yield


def row(uid, pct, pnl, eligible=True, trading=None) -> RankRow:
    pnl_d = Decimal(str(pnl))
    trading_d = Decimal(str(trading)) if trading is not None else pnl_d
    return RankRow(
        uid=uid,
        nickname="",
        last_balance=Decimal("100"),
        contest_pnl=pnl_d,
        trading_pnl=trading_d,
        return_pct=Decimal(str(pct)),
        trading_return_pct=trading_d,
        day_deposits=Decimal("50"),
        day_withdrawals=Decimal("0"),
        day_bonuses=Decimal("0"),
        basis=Decimal("100"),
        eligible=eligible,
        dq_reason="",
    )


def test_yield_sorts_desc():
    rows = [row(1, 10, 10), row(2, 40, 40), row(3, 5, 5)]
    assert [r.uid for r in sort_yield(rows)] == [2, 1, 3]


def test_loss_sorts_most_negative_trading_first():
    rows = [row(1, -10, -10), row(2, -80, -80), row(3, 5, 5)]
    assert [r.uid for r in sort_loss(rows)][0] == 2


def test_withdrawal_does_not_win_loss_nomination():
    green = row(9, 50, 50)
    withdrawn = row(1, -90, -90, trading=0)
    real_loss = row(2, -20, -20, trading=-20)
    winners = pick_winners(
        [green, withdrawn, real_loss],
        places=1,
        prize_yield=[100],
        prize_loss_pct=[15],
        loss_cap=Decimal("500"),
    )
    assert [w["uid"] for w in winners["yield"]] == [9]
    assert [w["uid"] for w in winners["loss"]] == [2]


def test_winner_exclusion_and_ineligible():
    rows = [
        row(1, 90, 90),
        row(2, 50, 50),
        row(3, 20, 20),
        row(4, -30, -30),
        row(5, -70, -70),
        row(9, 999, 999, eligible=False),
    ]
    winners = pick_winners(
        rows,
        places=3,
        prize_yield=[100, 50, 25],
        prize_loss_pct=[15, 10, 5],
        loss_cap=Decimal("500"),
    )
    assert [w["uid"] for w in winners["yield"]] == [1, 2, 3]
    assert [w["uid"] for w in winners["loss"]] == [5, 4]
    assert winners["loss"][0]["prize_amount"] == Decimal("70") * Decimal("15") / Decimal("100")


def test_negatives_never_win_yield():
    rows = [row(1, -100, -100), row(2, -50, -50), row(3, 10, 10)]
    winners = pick_winners(rows, 3, [100, 50, 25], [15, 10, 5], Decimal("500"))
    assert [w["uid"] for w in winners["yield"]] == [3]
    assert [w["uid"] for w in winners["loss"]] == [1, 2]


def test_yield_gap_to_first_and_top():
    from app.services.ranking import yield_target

    first = row(1, 20, 20)
    seventh = row(7, 5, 5)
    me = row(9, 2, 2)
    pool = [first] + [row(i, 10 - i, 10 - i) for i in range(2, 8)] + [me]
    # rebuild clean pool of 8
    pool = [
        row(1, 20, 20),
        row(2, 15, 15),
        row(3, 12, 12),
        row(4, 10, 10),
        row(5, 8, 8),
        row(6, 6, 6),
        row(7, 5, 5),
        me,
    ]
    g7 = yield_target(me, pool, 7)
    assert g7["already"] is False
    assert g7["need_pct"] > 0
    g1 = yield_target(me, pool, 1)
    assert g1["need_pnl"] > g7["need_pnl"]
    assert yield_target(first, pool, 1)["already"] is True


def test_loss_gap_counts_extra_drawdown():
    from app.services.ranking import loss_target

    deep = row(1, -50, -50)
    me = row(2, -5, -5)
    pool = [deep, me]
    g = loss_target(me, pool, 1)
    assert g["already"] is False
    assert g["need_pnl"] > 0
    assert loss_target(deep, pool, 1)["already"] is True


def test_no_loss_winners_when_all_green():
    rows = [row(1, 10, 10), row(2, 8, 8)]
    winners = pick_winners(rows, 3, [1, 1, 1], [15, 10, 5], Decimal("500"))
    assert winners["loss"] == []
