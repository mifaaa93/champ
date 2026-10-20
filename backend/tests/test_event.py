from datetime import datetime, timedelta, timezone
from datetime import date
from decimal import Decimal
import random
from types import SimpleNamespace

from app.services.event import (
    board_totals,
    combined_totals,
    dummy_live_events,
    dummy_uid,
    season_deposit_delta,
    merge_board,
    merge_nomination,
    place_pinned,
    eligible_real_totals,
    event_totals,
    min_event_deposit,
    neighbor_window,
    nudge_amount,
    overtake_events,
    pick_dummy_name,
    season_dep_from_points,
    sort_by_dep,
    sort_by_loss,
    sort_by_yield,
    turnover_from_info,
    visible_nominations,
)
from app.schemas import EventRegisterIn, SettingsPatch
from pydantic import ValidationError
import pytest


def test_sort_by_dep_assigns_ranks():
    ranked = sort_by_dep(
        [
            {"uid": 111111111, "name": "b", "dep": 10},
            {"uid": 222222222, "name": "a", "dep": 50},
            {"uid": 333333333, "name": "c", "dep": 50},
        ]
    )
    assert [r["uid"] for r in ranked] == [222222222, 333333333, 111111111]


def test_yield_ranking_prioritizes_profit_amount_over_percent():
    from app.services.event import sort_by_yield

    ranked = sort_by_yield(
        [
            {"uid": 1, "pnl": 2000, "return_pct": 200},
            {"uid": 2, "pnl": 150, "return_pct": 300},
        ]
    )
    assert [row["uid"] for row in ranked] == [1, 2]


def test_season_deposit_boundary_is_exact():
    assert season_deposit_delta(1000.10, None, 1050.10) == 50.0
    assert season_deposit_delta(None, 50.10, 100.10) == 50.0


def test_loss_showcase_tie_uses_visible_percent():
    rows = sort_by_loss([
        {"uid": -1, "dummy": True, "pnl": -80000, "return_pct": -16.6},
        {"uid": 123456789, "dummy": False, "pnl": -80000, "trading_return_pct": -16.2},
    ])
    assert rows[0]["uid"] == -1


def test_pinned_real_keeps_place_when_dummies_reorder():
    real = {"uid": 123456789, "dummy": False, "name": "real"}
    dummies = [
        {"uid": -1, "dummy": True, "name": "one"},
        {"uid": -2, "dummy": True, "name": "two"},
        {"uid": -3, "dummy": True, "name": "three"},
    ]
    for order in (dummies + [real], list(reversed(dummies)) + [real]):
        result = place_pinned(order, {123456789: 3})
        assert result[2]["uid"] == 123456789
        assert sorted(r["uid"] for r in result) == [-3, -2, -1, 123456789]
        assert [r["rank"] for r in result] == [1, 2, 3, 4]


def test_pinned_real_keeps_place_when_board_has_too_few_rows():
    from app.services.event import _public_top

    single = [{"uid": 123456789, "name": "real", "dep": 100, "dummy": False}]
    assert place_pinned(single, {123456789: 4}) == [{**single[0], "rank": 4}]
    two = [{"uid": -1, "dummy": True}, *single]
    assert [row["rank"] for row in place_pinned(two, {123456789: 4})] == [1, 4]
    assert place_pinned(single, {123456789: 1})[0]["rank"] == 1
    assert _public_top(place_pinned(single, {123456789: 4}), limit=3) == []
    assert _public_top(place_pinned(single, {123456789: 4}), limit=4)[0]["place"] == 4


def test_real_statistics_include_eligible_traders_without_nomination_result():
    entries = [
        {"uid": 123456789, "dep": 70, "pnl": 0, "in_ranking": True},
        {"uid": 123456790, "dep": 90, "pnl": 10, "in_ranking": True},
        {"uid": 123456791, "dep": 25, "pnl": 5, "in_ranking": False},
    ]
    assert eligible_real_totals(entries) == (2, 160)
    assert eligible_real_totals([]) == (0, 0)


def test_event_totals_adds_configured_dummies_and_real_accounts():
    boards = [
        [{"dummy": True, "dep": 100}, {"dummy": True, "dep": 200}],
        [{"dummy": True, "dep": 300}],
    ]
    real = [
        {"uid": 1, "dep": 50, "in_ranking": True},
        {"uid": 2, "dep": 25, "in_ranking": False},
    ]
    assert event_totals(boards, real) == (4, 650)


def test_uid_history_counts_days_not_championships():
    from app.services.history import day_history_summary

    first = date(2026, 10, 11)
    second = date(2026, 10, 12)
    results = [
        SimpleNamespace(day=first, place=1, prize_amount=Decimal("100")),
        SimpleNamespace(day=first, place=2, prize_amount=Decimal("50")),
        SimpleNamespace(day=second, place=1, prize_amount=Decimal("75")),
    ]
    assert day_history_summary(results, {first, second, date(2026, 10, 13)}) == {
        "participation_days": 3,
        "daily_first_places": 2,
        "daily_prizes_usdt": 225.0,
    }


def test_hidden_dummy_does_not_take_place():
    ranked = merge_nomination(
        [{"place": 1, "name": "hidden", "dep": 100, "hidden": True, "return_pct": 20},
         {"place": 2, "name": "visible", "dep": 50, "return_pct": 10}],
        [{"uid": 123456789, "name": "real", "dep": 100, "pnl": 50, "return_pct": 5}],
        "A",
    )
    assert [r["name"] for r in ranked] == ["real", "visible"]
    assert [r["rank"] for r in ranked] == [1, 2]


def test_pinned_real_can_enter_yield_board_without_positive_pnl():
    board = merge_nomination(
        [{"place": 1, "name": "demo", "dep": 100, "pnl": 50, "return_pct": 50}],
        [{"uid": 123456789, "name": "real", "dep": 10454, "pnl": 0, "return_pct": 0, "force_nomination": True}],
        "A",
    )
    assert any(row["uid"] == 123456789 for row in board)


def test_neighbor_window_includes_self():
    ranked = sort_by_dep(
        [{"uid": i, "name": str(i), "dep": 100 - i} for i in range(1, 8)]
    )
    win = neighbor_window(ranked, 4, 2)
    assert [r["uid"] for r in win] == [2, 3, 4, 5, 6]
    assert sum(1 for r in win if r["uid"] == 4) == 1


def test_turnover_reads_known_keys():
    assert turnover_from_info({"volume": "12.5"}) == 12.5
    assert turnover_from_info({}) == 0.0


def test_event_register_uid_must_be_9_or_10_digits():
    with pytest.raises(ValidationError):
        EventRegisterIn(uid=12345678, nickname="Rami")
    ok = EventRegisterIn(uid=123456789, nickname="Rami", telegram="https://t.me/rami_user")
    assert ok.telegram == "rami_user"
    assert EventRegisterIn(uid=123456789, nickname="Rami").telegram == ""


def test_merge_puts_real_above_dummy_when_dep_higher():
    board = merge_board(
        [
            {"place": 1, "name": "Ахмед", "dep": 150000, "turn": 1},
            {"place": 2, "name": "Улугбек", "dep": 35000, "turn": 1},
        ],
        [{"uid": 141917235, "name": "Тест", "dep": 40000, "turn": 0}],
    )
    assert [r["name"] for r in board] == ["Ахмед", "Тест", "Улугбек"]
    assert board[1]["dummy"] is False
    assert board[1]["rank"] == 2


def test_board_totals_count_dummies_and_reals():
    board = merge_board(
        [
            {"place": 1, "name": "Ахмед", "dep": 150000, "turn": 4_500_000},
            {"place": 2, "name": "Равшан", "dep": 120000, "turn": 3_800_000},
        ],
        [{"uid": 141917235, "name": "Тест", "dep": 10000, "turn": 2000}],
    )
    players, deposits, turnover = board_totals(board)
    assert players == 3
    assert deposits == 150000 + 120000 + 10000
    assert turnover == 4_500_000 + 3_800_000 + 2000


def test_overtake_dummy_emits_feed_event():
    old = merge_board(
        [{"place": 1, "name": "Ахмед", "dep": 100, "turn": 0}, {"place": 2, "name": "Тимур", "dep": 50, "turn": 0}],
        [{"uid": 141917235, "name": "Тест", "dep": 10, "turn": 0}],
    )
    new = merge_board(
        [{"place": 1, "name": "Ахмед", "dep": 100, "turn": 0}, {"place": 2, "name": "Тимур", "dep": 50, "turn": 0}],
        [{"uid": 141917235, "name": "Тест", "dep": 80, "turn": 0}],
    )
    events = overtake_events(old, new)
    assert any(e["action"] == "обогнал" and e["extra"] == "Тимур" for e in events)


def test_settings_accepts_event_fields():
    patch = SettingsPatch(event_name="CUP", prize_pool=5000, rami_url="https://t.me/x")
    assert patch.event_name == "CUP"
    assert patch.prize_pool == 5000


def test_settings_accepts_event_start_and_min_deposit():
    patch = SettingsPatch(event_start="2026-10-01T00:00:00+02:00", event_min_deposit=50)
    assert patch.event_start.endswith("+02:00")
    assert patch.event_min_deposit == 50


def test_event_min_deposit_rejects_below_fifty():
    with pytest.raises(ValidationError):
        SettingsPatch(event_min_deposit=49)


def test_season_dep_is_delta_inside_window():
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 11, tzinfo=timezone.utc)
    points = [
        (start - timedelta(days=1), 1000.0),
        (start + timedelta(days=2), 1300.0),
        (end - timedelta(hours=1), 1600.0),
    ]
    assert season_dep_from_points(points, start, end) == 600.0


def test_reals_below_min_stay_off_merged_board():
    min_dep = min_event_deposit({"event_min_deposit": 50})
    reals = [
        {"uid": 141917235, "name": "Мало", "dep": 49.99, "turn": 0, "in_ranking": 49.99 >= min_dep},
        {"uid": 141917236, "name": "Ок", "dep": 50, "turn": 10, "in_ranking": 50 >= min_dep},
    ]
    board = merge_board(
        [{"place": 1, "name": "Ахмед", "dep": 150000, "turn": 1}],
        [r for r in reals if r["in_ranking"]],
    )
    assert [r["name"] for r in board] == ["Ахмед", "Ок"]


def test_deposit_activity_keeps_amount_out_of_the_place():
    from app.services.event import _format_activity

    rows = _format_activity(
        [
            {
                "name": "Руслан",
                "action": "пополнил депозит на",
                "extra": "$9 249",
                "rank": 7,
                "scope": "B",
                "ts": 100,
            }
        ],
        100,
    )
    assert rows[0]["rank"] is None
    assert rows[0]["extra"] == "$9 249"
    assert rows[0]["scope"] == "B"


def test_activity_feed_limit_is_independent_of_ranking_depth():
    from app.services.event import _format_activity

    events = [
        {"name": f"Участник {i}", "action": "вошёл в турнир", "ts": 100}
        for i in range(12)
    ]
    assert len(_format_activity(events, 100)) == 6
    assert len(_format_activity(events, 100, 3)) == 3
    assert len(_format_activity(events, 100, 12)) == 12


def test_dummy_live_events_on_name_and_dep():
    old = merge_board(
        [{"place": 1, "name": "Ахмед", "dep": 1000, "turn": 0}, {"place": 2, "name": "Тимур", "dep": 800, "turn": 0}],
        [],
    )
    new = merge_board(
        [{"place": 1, "name": "Нурлан", "dep": 1000, "turn": 0}, {"place": 2, "name": "Тимур", "dep": 950, "turn": 0}],
        [],
    )
    events = dummy_live_events(old, new)
    assert any(e["action"] == "занял место" and e["name"] == "Нурлан" for e in events)
    deposit = next(e for e in events if e["action"] == "пополнил депозит на" and e["name"] == "Тимур")
    assert deposit["rank"] is None
    assert deposit["extra"].startswith("$")


def test_nudge_stays_at_least_fifty():
    rng = random.Random(1)
    assert nudge_amount(50, rng, lo=50) >= 50


def test_pick_dummy_name_avoids_taken():
    rng = random.Random(2)
    name = pick_dummy_name("Ахмед", {"Ахмед", "Равшан"}, rng)
    assert name not in {"Ахмед", "Равшан"}


def test_yield_board_ranks_by_return_and_keeps_real_on_tie():
    board = merge_nomination(
        [
            {"place": 1, "name": "Ахмед", "dep": 1000, "pnl": 100, "return_pct": 10},
            {"place": 2, "name": "Тимур", "dep": 1000, "pnl": 50, "return_pct": 5},
        ],
        [{"uid": 141917235, "name": "Тест", "dep": 80, "pnl": 40, "return_pct": 10}],
        "A",
    )
    assert [r["name"] for r in board] == ["Ахмед", "Тимур", "Тест"]
    tied = merge_nomination(
        [{"place": 1, "name": "Ахмед", "dep": 1000, "pnl": 100, "return_pct": 10}],
        [{"uid": 141917235, "name": "Тест", "dep": 80, "pnl": 100, "return_pct": 10}],
        "A",
    )
    assert [r["name"] for r in tied] == ["Тест", "Ахмед"]
    assert tied[0]["dummy"] is False
    assert dummy_uid(1, "A") == -1


def test_loss_board_ranks_biggest_loss_and_skips_profit():
    board = merge_nomination(
        [
            {"place": 1, "name": "Нурлан", "dep": 1000, "pnl": -500, "return_pct": -20},
            {"place": 2, "name": "Ерлан", "dep": 1000, "pnl": -100, "return_pct": -5},
        ],
        [
            {"uid": 141917235, "name": "Плюс", "dep": 80, "pnl": 40, "return_pct": 10},
            {"uid": 141917236, "name": "Минус", "dep": 90, "pnl": -250, "return_pct": -12},
        ],
        "B",
    )
    assert [r["name"] for r in board] == ["Нурлан", "Минус", "Ерлан"]
    assert dummy_uid(1, "B") == -101
    ranked = sort_by_loss(
        [
            {"uid": 1, "pnl": -10, "dummy": False},
            {"uid": 2, "pnl": -40, "dummy": True},
        ]
    )
    assert [r["uid"] for r in ranked] == [2, 1]
    assert sort_by_yield([{"uid": 1, "return_pct": 1, "pnl": 1}, {"uid": 2, "return_pct": 9, "pnl": 1}])[0]["uid"] == 2


def test_withdrawal_does_not_enter_the_loss_board():
    reals = [
        {
            "uid": 141917235,
            "name": "Вывел",
            "dep": 100,
            "pnl": -100,
            "trading_pnl": 20,
            "return_pct": -10,
            "trading_return_pct": 4,
        }
    ]
    assert merge_nomination([], reals, "B") == []
    assert merge_nomination([], reals, "A") == []


def test_loss_board_uses_trading_pnl():
    board = merge_nomination(
        [],
        [
            {
                "uid": 141917235,
                "name": "Торговля",
                "dep": 100,
                "pnl": -200,
                "trading_pnl": -40,
                "return_pct": -20,
                "trading_return_pct": -8,
            }
        ],
        "B",
    )
    assert board[0]["name"] == "Торговля"
    assert board[0]["pnl"] == -40


def test_blocked_real_stays_off_both_boards():
    reals = [
        {
            "uid": 141917235,
            "name": "Бан",
            "dep": 100,
            "pnl": 50,
            "trading_pnl": -20,
            "return_pct": 10,
            "blocked": True,
        }
    ]
    assert merge_nomination([], reals, "A") == []
    assert merge_nomination([], reals, "B") == []


def test_rank_outside_the_window_is_not_a_new_entry():
    board = [
        {"uid": i, "rank": i, "name": f"n{i}", "dummy": False, "dep": 1}
        for i in range(1, 101)
    ]
    assert overtake_events(board[:80], board) == []


def test_season_deposit_needs_two_points_without_a_baseline():
    assert season_deposit_delta(1000.0, 1300.0, 1600.0) == 600.0
    assert season_deposit_delta(None, 1300.0, 1600.0) == 300.0
    assert season_deposit_delta(None, 1300.0, 1300.0) is None


def test_visible_nominations_fallback_when_both_off():
    assert visible_nominations({"show_nomination_a": False, "show_nomination_b": True}) == (False, True)
    assert visible_nominations({"show_nomination_a": False, "show_nomination_b": False}) == (True, True)


def test_combined_totals_count_real_once():
    a = [{"uid": -1, "dummy": True, "dep": 100, "turn": 10}, {"uid": 5, "dummy": False, "dep": 50, "turn": 5}]
    b = [{"uid": -101, "dummy": True, "dep": 80, "turn": 8}, {"uid": 5, "dummy": False, "dep": 50, "turn": 5}]
    players, deposits, turnover = combined_totals([a, b])
    assert players == 3
    assert deposits == 230
    assert turnover == 23


def test_settings_accepts_nomination_flags():
    patch = SettingsPatch(show_nomination_a=True, show_nomination_b=False)
    assert patch.show_nomination_a is True
    assert patch.show_nomination_b is False
