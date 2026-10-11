from app.services.event import neighbor_window, sort_by_dep, turnover_from_info
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


def test_settings_accepts_event_fields():
    patch = SettingsPatch(event_name="CUP", prize_pool=5000, rami_url="https://t.me/x")
    assert patch.event_name == "CUP"
    assert patch.prize_pool == 5000
