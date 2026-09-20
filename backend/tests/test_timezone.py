from datetime import datetime

from app.timezone import DUBAI, dubai_today, is_final_post_window, is_freeze_window, seconds_until_dubai_midnight


def test_dubai_day_rolls_at_midnight_local():
    before = datetime(2026, 9, 19, 23, 59, tzinfo=DUBAI)
    after = datetime(2026, 9, 20, 0, 0, tzinfo=DUBAI)
    assert dubai_today(before).isoformat() == "2026-09-19"
    assert dubai_today(after).isoformat() == "2026-09-20"


def test_freeze_and_final_windows():
    assert is_freeze_window(datetime(2026, 9, 19, 23, 59, 10, tzinfo=DUBAI))
    assert not is_freeze_window(datetime(2026, 9, 19, 23, 58, tzinfo=DUBAI))
    assert is_final_post_window(datetime(2026, 9, 20, 0, 5, tzinfo=DUBAI))
    assert not is_final_post_window(datetime(2026, 9, 20, 1, 0, tzinfo=DUBAI))


def test_seconds_to_close():
    at = datetime(2026, 9, 19, 23, 0, 0, tzinfo=DUBAI)
    assert seconds_until_dubai_midnight(at) == 3600
