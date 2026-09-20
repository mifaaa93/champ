from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DUBAI = ZoneInfo("Asia/Dubai")
UTC = ZoneInfo("UTC")


def now_dubai() -> datetime:
    return datetime.now(DUBAI)


def now_utc() -> datetime:
    return datetime.now(UTC)


def dubai_today(at: datetime | None = None) -> date:
    return (at.astimezone(DUBAI) if at else now_dubai()).date()


def dubai_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=DUBAI)
    end = start + timedelta(days=1)
    return start, end


def dubai_day_end(day: date) -> datetime:
    start, end = dubai_day_bounds(day)
    return end


def seconds_until_dubai_midnight(at: datetime | None = None) -> int:
    moment = at.astimezone(DUBAI) if at else now_dubai()
    _, end = dubai_day_bounds(moment.date())
    return max(0, int((end - moment).total_seconds()))


def is_freeze_window(at: datetime | None = None) -> bool:
    moment = at.astimezone(DUBAI) if at else now_dubai()
    return moment.hour == 23 and moment.minute >= 59


def is_final_post_window(at: datetime | None = None) -> bool:
    moment = at.astimezone(DUBAI) if at else now_dubai()
    return moment.hour == 0 and moment.minute < 8
