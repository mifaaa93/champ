from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# Partners statistics calendar is UTC+2 year-round (no DST).
CHAMP_TZ = ZoneInfo("Africa/Johannesburg")
TZ_NAME = "Africa/Johannesburg"
TZ_LABEL = "UTC+2"
UTC = ZoneInfo("UTC")


def now_champ() -> datetime:
    return datetime.now(CHAMP_TZ)


def now_utc() -> datetime:
    return datetime.now(UTC)


def champ_today(at: datetime | None = None) -> date:
    return (at.astimezone(CHAMP_TZ) if at else now_champ()).date()


def champ_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=CHAMP_TZ)
    end = start + timedelta(days=1)
    return start, end


def champ_day_end(day: date) -> datetime:
    _, end = champ_day_bounds(day)
    return end


def seconds_until_midnight(at: datetime | None = None) -> int:
    moment = at.astimezone(CHAMP_TZ) if at else now_champ()
    _, end = champ_day_bounds(moment.date())
    return max(0, int((end - moment).total_seconds()))


def is_freeze_window(at: datetime | None = None) -> bool:
    moment = at.astimezone(CHAMP_TZ) if at else now_champ()
    return moment.hour == 23 and moment.minute >= 59


def is_final_post_window(at: datetime | None = None) -> bool:
    moment = at.astimezone(CHAMP_TZ) if at else now_champ()
    return moment.hour == 0 and moment.minute < 8


# Old names — call sites still use them.
now_dubai = now_champ
dubai_today = champ_today
dubai_day_bounds = champ_day_bounds
dubai_day_end = champ_day_end
seconds_until_dubai_midnight = seconds_until_midnight
