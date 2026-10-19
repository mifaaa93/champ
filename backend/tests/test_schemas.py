import pytest
from pydantic import ValidationError

from decimal import Decimal

from app.schemas import ProfilePatch, RegisterIn, SettingsPatch, day_cash


def test_register_rejects_tiny_uid():
    with pytest.raises(ValidationError):
        RegisterIn(uid=12)


def test_profile_patch_preserves_omitted_field():
    assert ProfilePatch(telegram="@rami_user").nickname is None
    assert ProfilePatch(nickname="Иван").telegram is None


def test_register_rejects_bad_telegram():
    with pytest.raises(ValidationError):
        RegisterIn(uid=114653273, telegram="https://t.me/x")


def test_register_accepts_telegram_link_at_and_plain():
    from app.schemas import normalize_telegram

    assert normalize_telegram("https://t.me/rami_user") == "rami_user"
    assert normalize_telegram("https://t.me/rami_user/") == "rami_user"
    assert normalize_telegram("@rami_user") == "rami_user"
    assert normalize_telegram("rami_user") == "rami_user"
    assert RegisterIn(uid=114653273, telegram="t.me/rami_user").telegram == "rami_user"


def test_settings_rejects_percent_over_100():
    with pytest.raises(ValidationError):
        SettingsPatch(prize_places=3, prize_yield=[1, 1, 1], prize_loss_pct=[15, 10, 150])


def test_day_cash_prefers_statistics_when_snapshot_missed_deposit():
    assert day_cash(Decimal("0"), Decimal("1177.36")) == Decimal("1177.36")


def test_settings_accepts_telegram_credentials():
    patch = SettingsPatch(tg_bot_token="123:abc", tg_chat_id="-1001")
    assert patch.tg_bot_token == "123:abc"
    assert patch.tg_chat_id == "-1001"


def test_admin_view_hides_bot_token():
    from app.settings_service import admin_view

    view = admin_view({"tg_bot_token": "123456:SECRET99", "tg_chat_id": "-1", "top_n": 7})
    assert view["tg_bot_token"] == ""
    assert view["tg_bot_configured"] is True
    assert view["tg_bot_token_tail"] == "ET99"
    assert view["tg_chat_id"] == "-1"


def test_register_accepts_cyrillic_nick():
    assert RegisterIn(uid=114653273, nickname="Иван").nickname == "Иван"


def test_settings_reject_nan_prize():
    with pytest.raises(ValidationError):
        SettingsPatch(prize_yield=[float("nan")])


def test_settings_reject_bad_event_date():
    with pytest.raises(ValidationError):
        SettingsPatch(event_start="not-a-date")


def test_settings_reject_start_after_end():
    with pytest.raises(ValidationError):
        SettingsPatch(
            event_start="2026-10-11T00:00:00+02:00",
            event_end="2026-10-01T00:00:00+02:00",
        )


def test_merged_prizes_must_match_places_even_across_patches():
    from app.settings_service import assert_saved_settings

    current = {"prize_places": 10, "prize_yield": [100, 50, 25], "prize_loss_pct": [15, 10, 5]}
    with pytest.raises(ValueError):
        assert_saved_settings(current)


def test_settings_places_must_match_prizes():
    with pytest.raises(ValidationError):
        SettingsPatch(prize_places=3, prize_yield=[100, 50])
