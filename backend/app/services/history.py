from datetime import date
from decimal import Decimal
from typing import Protocol


class DayOutcome(Protocol):
    day: date
    place: int
    prize_amount: Decimal


def day_history_summary(results: list[DayOutcome], participation_days: set[date]) -> dict:
    """Only day-level records exist; do not claim these are separate championships."""
    days = participation_days | {item.day for item in results}
    return {
        "participation_days": len(days),
        "daily_first_places": sum(item.place == 1 for item in results),
        "daily_prizes_usdt": round(sum(float(item.prize_amount or 0) for item in results), 2),
    }
