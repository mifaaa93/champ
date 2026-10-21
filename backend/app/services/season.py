"""Capture the end-of-season leaderboard without recalculating past standings."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SeasonResult
from app.services.event import event_bounds
from app.settings_service import get_settings, job_get
from app.timezone import now_champ, now_utc


def final_payload(cfg: dict, live: dict) -> dict:
    """Copy the *last published* complete standings and prize configuration."""
    return {
        "name": str(cfg.get("event_name") or "PO CHAMPIONSHIP"),
        "source": "last_live_board",
        "board_updated_at": live.get("computed_at"),
        "top_visible": int(cfg.get("top_visible") or 10),
        "show_a": bool(cfg.get("show_nomination_a", True)),
        "show_b": bool(cfg.get("show_nomination_b", True)),
        "prize_pool": float(cfg.get("prize_pool") or 0),
        "prize_table": deepcopy(cfg.get("prize_table") or []),
        "yield": deepcopy(live.get("ranks_a") or []),
        "loss": deepcopy(live.get("ranks_b") or []),
    }


async def finalize_season(session: AsyncSession, at: datetime | None = None) -> SeasonResult | None:
    """Idempotently freeze a season after its end; never rewrite existing results.

    If the worker was offline at the deadline, use the last durable live board,
    not a newly calculated board based on activity after the deadline.
    """
    cfg = await get_settings(session)
    start, end = event_bounds(cfg)
    now = at or now_champ()
    if now < end:
        return None

    conn = await session.connection()
    if conn.dialect.name == "postgresql":
        # Serialize with refresh_event_boards: a refresh already in progress
        # must finish publishing before we capture its last eligible board.
        await session.execute(text("SELECT pg_advisory_xact_lock(814201)"))

    existing = (await session.execute(
        select(SeasonResult).where(SeasonResult.event_end == end)
    )).scalar_one_or_none()
    if existing is not None:
        await session.commit()
        return existing

    live = await job_get(session, "event_live")
    if live.get("ranks_a") is None or live.get("ranks_b") is None:
        # No reliable pre-deadline standings exist. Do not silently announce
        # a reconstructed current leaderboard as the historical final.
        await session.commit()
        return None
    if live.get("event_end") != end.isoformat():
        await session.commit()
        return None
    computed_at = live.get("computed_at")
    if not computed_at or datetime.fromisoformat(computed_at) > end:
        await session.commit()
        return None
    payload = final_payload(cfg, live)

    row = SeasonResult(
        event_start=start,
        event_end=end,
        frozen_at=now_utc(),
        payload=payload,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row
