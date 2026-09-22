import pytest
from pydantic import ValidationError

from decimal import Decimal

from app.schemas import RegisterIn, SettingsPatch, day_cash


def test_register_rejects_tiny_uid():
    with pytest.raises(ValidationError):
        RegisterIn(uid=12)


def test_register_rejects_bad_telegram():
    with pytest.raises(ValidationError):
        RegisterIn(uid=114653273, telegram="https://t.me/x")


def test_settings_rejects_percent_over_100():
    with pytest.raises(ValidationError):
        SettingsPatch(prize_places=3, prize_yield=[1, 1, 1], prize_loss_pct=[15, 10, 150])


def test_day_cash_prefers_statistics_when_snapshot_missed_deposit():
    assert day_cash(Decimal("0"), Decimal("1177.36")) == Decimal("1177.36")


def test_settings_places_must_match_prizes():
    with pytest.raises(ValidationError):
        SettingsPatch(prize_places=3, prize_yield=[100, 50])
