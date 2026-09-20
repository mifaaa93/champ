from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    uid: int = Field(ge=1)
    nickname: str = ""
    telegram: str = ""


class SettingsPatch(BaseModel):
    top_n: int | None = Field(default=None, ge=1, le=50)
    min_day_deposit: float | None = Field(default=None, ge=0)
    publish_interval_minutes: int | None = Field(default=None, ge=15, le=180)
    prize_yield: list[float] | None = None
    prize_loss_pct: list[float] | None = None
    loss_comp_cap: float | None = Field(default=None, ge=0)
    require_trade: bool | None = None
    prize_places: int | None = Field(default=None, ge=1, le=10)


def dec(value: Decimal | int | float | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def row_out(row: Any, snapshot_ts: datetime | None = None) -> dict:
    return {
        "uid": row.uid,
        "nickname": getattr(row, "nickname", "") or "",
        "balance": dec(row.last_balance),
        "pnl": dec(row.contest_pnl),
        "return_pct": dec(row.return_pct),
        "deposits": dec(row.day_deposits),
        "withdrawals": dec(row.day_withdrawals),
        "bonuses": dec(row.day_bonuses),
        "basis": dec(row.basis),
        "eligible": row.eligible,
        "dq_reason": row.dq_reason,
        "snapshot_ts": snapshot_ts.isoformat() if snapshot_ts else None,
    }
