from datetime import datetime

from app.timezone import (
    CHAMP_TZ,
    champ_today,
    is_final_post_window,
    is_freeze_window,
    seconds_until_midnight,
)


def test_day_rolls_at_midnight_utc_plus_2():
    before = datetime(2026, 9, 19, 23, 59, tzinfo=CHAMP_TZ)
    after = datetime(2026, 9, 20, 0, 0, tzinfo=CHAMP_TZ)
    assert champ_today(before).isoformat() == "2026-09-19"
    assert champ_today(after).isoformat() == "2026-09-20"


def test_freeze_and_final_windows():
    assert is_freeze_window(datetime(2026, 9, 19, 23, 59, 10, tzinfo=CHAMP_TZ))
    assert not is_freeze_window(datetime(2026, 9, 19, 23, 58, tzinfo=CHAMP_TZ))
    assert is_final_post_window(datetime(2026, 9, 20, 0, 5, tzinfo=CHAMP_TZ))
    assert not is_final_post_window(datetime(2026, 9, 20, 1, 0, tzinfo=CHAMP_TZ))


def test_seconds_to_close():
    at = datetime(2026, 9, 19, 23, 0, 0, tzinfo=CHAMP_TZ)
    assert seconds_until_midnight(at) == 3600
