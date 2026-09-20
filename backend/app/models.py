from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


Money = Numeric(18, 4)


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    nickname: Mapped[str] = mapped_column(String(64), default="")
    telegram: Mapped[str] = mapped_column(String(64), default="")
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Trader(Base):
    __tablename__ = "traders"

    uid: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="")
    self_excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_user_info: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Snapshot(Base):
    __tablename__ = "snapshots"
    __table_args__ = (UniqueConstraint("uid", "ts", name="uq_snapshot_uid_ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[int] = mapped_column(BigInteger, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    balance: Mapped[Decimal] = mapped_column(Money)
    sum_deposits: Mapped[Decimal] = mapped_column(Money)
    sum_withdrawals: Mapped[Decimal] = mapped_column(Money)
    sum_bonuses: Mapped[Decimal] = mapped_column(Money)
    count_deposits: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="")
    self_excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class DayLedger(Base):
    __tablename__ = "day_ledgers"
    __table_args__ = (UniqueConstraint("day", "uid", name="uq_ledger_day_uid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    uid: Mapped[int] = mapped_column(BigInteger, index=True)
    start_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("snapshots.id"), nullable=True
    )
    last_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("snapshots.id"), nullable=True
    )
    start_balance: Mapped[Decimal] = mapped_column(Money, default=0)
    last_balance: Mapped[Decimal] = mapped_column(Money, default=0)
    day_deposits: Mapped[Decimal] = mapped_column(Money, default=0)
    day_withdrawals: Mapped[Decimal] = mapped_column(Money, default=0)
    day_bonuses: Mapped[Decimal] = mapped_column(Money, default=0)
    stats_depo_sum: Mapped[Decimal] = mapped_column(Money, default=0)
    stats_wdrw_sum: Mapped[Decimal] = mapped_column(Money, default=0)
    stats_trades: Mapped[int] = mapped_column(Integer, default=0)
    contest_pnl: Mapped[Decimal] = mapped_column(Money, default=0)
    trading_pnl: Mapped[Decimal] = mapped_column(Money, default=0)
    basis: Mapped[Decimal] = mapped_column(Money, default=0)
    return_pct: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    status: Mapped[str] = mapped_column(String(32), default="")
    self_excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    registered: Mapped[bool] = mapped_column(Boolean, default=False)
    dq_reason: Mapped[str] = mapped_column(String(64), default="")
    reconcile_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DayResult(Base):
    __tablename__ = "day_results"
    __table_args__ = (
        UniqueConstraint("day", "nomination", "place", name="uq_result_place"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    nomination: Mapped[str] = mapped_column(String(16))
    place: Mapped[int] = mapped_column(Integer)
    uid: Mapped[int] = mapped_column(BigInteger)
    metric: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    pnl: Mapped[Decimal] = mapped_column(Money)
    prize_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    prize_note: Mapped[str] = mapped_column(String(128), default="")
    frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class JobState(Base):
    __tablename__ = "job_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, default=dict)  # noqa: RUF012
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PublishLog(Base):
    __tablename__ = "publish_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(32))
    day: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
