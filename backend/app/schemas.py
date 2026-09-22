import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

NICK_RE = re.compile(r"^[\w.\- ]{1,32}$", re.UNICODE)
TG_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")


class RegisterIn(BaseModel):
    uid: int = Field(ge=100_000, le=9_999_999_999)
    nickname: str = Field(default="", max_length=32)
    telegram: str = Field(default="", max_length=64)
    website: str = Field(default="", max_length=200)

    @field_validator("nickname")
    @classmethod
    def clean_nick(cls, value: str) -> str:
        value = value.strip()
        if value and not NICK_RE.fullmatch(value):
            raise ValueError("Ник: буквы, цифры, пробел, точка, _ или -")
        return value

    @field_validator("telegram")
    @classmethod
    def clean_tg(cls, value: str) -> str:
        value = value.strip().lstrip("@")
        if value and not TG_RE.fullmatch(value):
            raise ValueError("Telegram: username без ссылки, 5–32 символа")
        return value


class ProfilePatch(BaseModel):
    nickname: str = Field(default="", max_length=32)
    telegram: str = Field(default="", max_length=64)

    @field_validator("nickname")
    @classmethod
    def clean_nick(cls, value: str) -> str:
        return RegisterIn.clean_nick(value)

    @field_validator("telegram")
    @classmethod
    def clean_tg(cls, value: str) -> str:
        return RegisterIn.clean_tg(value)


class SettingsPatch(BaseModel):
    top_n: int | None = Field(default=None, ge=1, le=50)
    min_day_deposit: float | None = Field(default=None, ge=1, le=1_000_000)
    publish_interval_minutes: int | None = Field(default=None, ge=15, le=180)
    prize_yield: list[float] | None = None
    prize_loss_pct: list[float] | None = None
    loss_comp_cap: float | None = Field(default=None, ge=0, le=1_000_000)
    require_trade: bool | None = None
    prize_places: int | None = Field(default=None, ge=1, le=10)
    min_return_pct: float | None = Field(default=None, ge=-1000, le=10000)
    tg_hourly_header: str | None = Field(default=None, max_length=500)
    tg_yield_title: str | None = Field(default=None, max_length=200)
    tg_yield_row: str | None = Field(default=None, max_length=400)
    tg_yield_empty: str | None = Field(default=None, max_length=400)
    tg_loss_title: str | None = Field(default=None, max_length=200)
    tg_loss_row: str | None = Field(default=None, max_length=400)
    tg_loss_empty: str | None = Field(default=None, max_length=400)
    tg_footer: str | None = Field(default=None, max_length=500)
    tg_final_header: str | None = Field(default=None, max_length=500)
    tg_final_yield_row: str | None = Field(default=None, max_length=400)
    tg_final_loss_row: str | None = Field(default=None, max_length=400)

    @field_validator("prize_yield")
    @classmethod
    def yield_ok(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return value
        if not value or len(value) > 10:
            raise ValueError("Призы доходности: от 1 до 10 мест")
        if any(x < 0 or x > 1_000_000 for x in value):
            raise ValueError("Сумма приза 0–1 000 000")
        return value

    @field_validator("prize_loss_pct")
    @classmethod
    def loss_ok(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return value
        if not value or len(value) > 10:
            raise ValueError("Проценты просадки: от 1 до 10 мест")
        if any(x < 0 or x > 100 for x in value):
            raise ValueError("Процент компенсации 0–100")
        return value

    @model_validator(mode="after")
    def lengths(self) -> "SettingsPatch":
        places = self.prize_places
        if places is None:
            return self
        if self.prize_yield is not None and len(self.prize_yield) != places:
            raise ValueError("Число призов доходности должно совпадать с числом мест")
        if self.prize_loss_pct is not None and len(self.prize_loss_pct) != places:
            raise ValueError("Число процентов просадки должно совпадать с числом мест")
        return self


def dec(value: Decimal | int | float | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def day_cash(snapshot_delta: Decimal | None, stats: Decimal | None) -> Decimal:
    a = snapshot_delta or Decimal("0")
    b = stats or Decimal("0")
    return a if a >= b else b


def row_out(
    row: Any,
    snapshot_ts: datetime | None = None,
    start_ts: datetime | None = None,
) -> dict:
    deposits = day_cash(row.day_deposits, getattr(row, "stats_depo_sum", None))
    withdrawals = day_cash(row.day_withdrawals, getattr(row, "stats_wdrw_sum", None))
    return {
        "uid": row.uid,
        "nickname": getattr(row, "nickname", "") or "",
        "balance": dec(row.last_balance),
        "start_balance": dec(getattr(row, "start_balance", None)),
        "pnl": dec(row.contest_pnl),
        "trading_pnl": dec(getattr(row, "trading_pnl", None)),
        "return_pct": dec(row.return_pct),
        "deposits": dec(deposits),
        "withdrawals": dec(withdrawals),
        "bonuses": dec(row.day_bonuses),
        "basis": dec(row.basis),
        "eligible": row.eligible,
        "dq_reason": row.dq_reason,
        "start_ts": start_ts.isoformat() if start_ts else None,
        "snapshot_ts": snapshot_ts.isoformat() if snapshot_ts else None,
    }
