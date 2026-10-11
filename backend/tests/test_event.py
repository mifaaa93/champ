from datetime import datetime, timedelta, timezone
import random

from app.services.event import (
    board_totals,
    dummy_live_events,
    merge_board,
    min_event_deposit,
    neighbor_window,
    nudge_amount,
    overtake_events,
    pick_dummy_name,
    season_dep_from_points,
    sort_by_dep,
    turnover_from_info,
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
    assert [r["rank"] for r in ranked] == [1, 2, 3]


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
    EventRegisterIn(uid=123456789, nickname="Rami")


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
    assert any(e["action"] == "пополнил депозит на" and e["name"] == "Тимур" for e in events)


def test_nudge_stays_at_least_fifty():
    rng = random.Random(1)
    assert nudge_amount(50, rng, lo=50) >= 50


def test_pick_dummy_name_avoids_taken():
    rng = random.Random(2)
    name = pick_dummy_name("Ахмед", {"Ахмед", "Равшан"}, rng)
    assert name not in {"Ахмед", "Равшан"}
