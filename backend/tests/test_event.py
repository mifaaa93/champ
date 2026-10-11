from app.services.event import (
    board_totals,
    merge_board,
    neighbor_window,
    overtake_events,
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
    players, turnover = board_totals(board)
    assert players == 3
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
