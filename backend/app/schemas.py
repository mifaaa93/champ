import math
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

NICK_RE = re.compile(r"^[\w.\- ]{1,32}$", re.UNICODE)
TG_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")
TG_LINK_RE = re.compile(r"^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/", re.IGNORECASE)


def normalize_telegram(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    raw = raw.split("?")[0].split("#")[0].strip().strip("/")
    raw = TG_LINK_RE.sub("", raw).strip().strip("/")
    if raw.lower().startswith("s/"):
        raw = raw[2:]
    raw = raw.lstrip("@").strip().split("/")[0]
    if raw and not TG_RE.fullmatch(raw):
        raise ValueError("Telegram: ссылка t.me, @username или username (5–32 символа)")
    return raw


class RegisterIn(BaseModel):
    uid: int = Field(ge=100_000, le=9_999_999_999)
    nickname: str = Field(default="", max_length=32)
    telegram: str = Field(default="", max_length=200)
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
        return normalize_telegram(value)


class ProfilePatch(BaseModel):
    nickname: str = Field(default="", max_length=32)
    telegram: str = Field(default="", max_length=200)

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
    prize_places: int | None = Field(default=None, ge=1, le=20)
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
    event_name: str | None = Field(default=None, max_length=64)
    event_start: str | None = Field(default=None, max_length=64)
    event_end: str | None = Field(default=None, max_length=64)
    event_min_deposit: float | None = Field(default=None, ge=50, le=1_000_000)
    dummy_tick_minutes: float | None = Field(default=None, ge=0.5, le=1440)
    prize_pool: float | None = Field(default=None, ge=0, le=10_000_000)
    prize_table: list[dict] | None = None
    stats_players: int | None = Field(default=None, ge=0, le=10_000_000)
    stats_turnover: float | None = Field(default=None, ge=0, le=10_000_000_000)
    top_visible: int | None = Field(default=None, ge=3, le=80)
    telegram_channel_url: str | None = Field(default=None, max_length=300)
    rami_url: str | None = Field(default=None, max_length=300)
    event_rules: list[str] | None = None
    activity: list[dict] | None = None
    tg_bot_token: str | None = Field(default=None, max_length=200)
    tg_chat_id: str | None = Field(default=None, max_length=80)
    show_nomination_a: bool | None = None
    show_nomination_b: bool | None = None
    settings_version: int | None = Field(default=None, ge=0)

    @field_validator("event_start", "event_end")
    @classmethod
    def event_dt(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return value
        try:
            datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Дата чемпионата: ISO, часовой пояс UTC+2") from exc
        return value

    @field_validator("prize_yield")
    @classmethod
    def yield_ok(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return value
        if not value or len(value) > 20:
            raise ValueError("Призы доходности: от 1 до 20 мест")
        if any((isinstance(x, float) and not math.isfinite(x)) or x < 0 or x > 1_000_000 for x in value):
            raise ValueError("Сумма приза 0–1 000 000")
        return value

    @field_validator("prize_loss_pct")
    @classmethod
    def loss_ok(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return value
        if not value or len(value) > 20:
            raise ValueError("Проценты просадки: от 1 до 20 мест")
        if any((isinstance(x, float) and not math.isfinite(x)) or x < 0 or x > 100 for x in value):
            raise ValueError("Процент компенсации 0–100")
        return value

    @model_validator(mode="after")
    def lengths(self) -> "SettingsPatch":
        for name in (
            "min_day_deposit",
            "loss_comp_cap",
            "min_return_pct",
            "event_min_deposit",
            "dummy_tick_minutes",
            "prize_pool",
            "stats_turnover",
        ):
            value = getattr(self, name)
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{name}: нужно конечное число")
        places = self.prize_places
        if self.event_start and self.event_end:
            start = datetime.fromisoformat(str(self.event_start).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(self.event_end).replace("Z", "+00:00"))
            if start.tzinfo is None:
                start = start.replace(tzinfo=end.tzinfo)
            if end.tzinfo is None:
                end = end.replace(tzinfo=start.tzinfo)
            if start >= end:
                raise ValueError("Старт чемпионата должен быть раньше окончания")
        if places is None:
            return self
        if self.prize_yield is not None and len(self.prize_yield) != places:
            raise ValueError("Число призов доходности должно совпадать с числом мест")
        if self.prize_loss_pct is not None and len(self.prize_loss_pct) != places:
            raise ValueError("Число процентов просадки должно совпадать с числом мест")
        return self


class EventRegisterIn(BaseModel):
    uid: int = Field(ge=100_000_000, le=9_999_999_999)
    nickname: str = Field(min_length=1, max_length=32)
    telegram: str = Field(default="", max_length=200)
    website: str = Field(default="", max_length=200)

    @field_validator("nickname")
    @classmethod
    def clean_nick(cls, value: str) -> str:
        value = RegisterIn.clean_nick(value)
        if not value:
            raise ValueError("Введи имя")
        return value

    @field_validator("telegram")
    @classmethod
    def clean_tg(cls, value: str) -> str:
        return normalize_telegram(value)


class ShowcaseIn(BaseModel):
    rows: list[dict] = []
    board: str | None = Field(default=None, max_length=1)
    boards: dict | None = None


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
