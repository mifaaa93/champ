from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services import season
from app.services.season import final_payload


def test_final_payload_keeps_all_ranks_and_prize_configuration():
    board = [{"uid": 123456789, "name": "Trader", "rank": 25, "pnl": 100}]
    cfg = {
        "event_name": "October",
        "top_visible": 10,
        "prize_pool": 8000,
        "prize_table": [{"place": "1 место", "amount": 2500}],
    }
    live = {"ranks_a": board, "ranks_b": [], "computed_at": "2026-10-25T07:59:00+02:00"}
    result = final_payload(cfg, live)
    assert result["yield"][0]["rank"] == 25  # Not limited to visible top 10.
    assert result["prize_pool"] == 8000
    board[0]["pnl"] = 0
    cfg["prize_table"][0]["amount"] = 0
    assert result["yield"][0]["pnl"] == 100
    assert result["prize_table"][0]["amount"] == 2500


class FakeSession:
    def __init__(self):
        self.saved = None
        self.commits = 0
        self.added = 0

    async def connection(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    async def execute(self, stmt):
        return SimpleNamespace(scalar_one_or_none=lambda: self.saved)

    def add(self, row):
        self.saved = row
        self.added += 1

    async def commit(self):
        self.commits += 1

    async def refresh(self, row):
        row.id = 1


@pytest.mark.asyncio
async def test_finalization_only_after_end_and_never_rewrites(monkeypatch):
    start = datetime(2026, 10, 11, 8, tzinfo=timezone.utc)
    end = start + timedelta(days=14)
    cfg = {"event_name": "October", "prize_table": [], "prize_pool": 5000}
    board = {"ranks_a": [], "ranks_b": [], "event_start": start.isoformat(), "event_end": end.isoformat(),
             "computed_at": (end - timedelta(seconds=10)).isoformat()}

    async def get_settings(_session):
        return cfg

    async def job_get(_session, _key):
        return board

    monkeypatch.setattr(season, "get_settings", get_settings)
    monkeypatch.setattr(season, "event_bounds", lambda _cfg: (start, end))
    monkeypatch.setattr(season, "job_get", job_get)
    session = FakeSession()
    assert await season.finalize_season(session, end - timedelta(seconds=1)) is None
    assert session.added == 0
    first = await season.finalize_season(session, end)
    assert first is not None and first.payload["yield"] == []
    cfg["prize_pool"] = 100
    second = await season.finalize_season(session, end + timedelta(days=1))
    assert second is first and second.payload["prize_pool"] == 5000
    assert session.added == 1


@pytest.mark.asyncio
async def test_finalization_rejects_board_from_other_season(monkeypatch):
    end = datetime(2026, 10, 25, tzinfo=timezone.utc)

    async def get_settings(_session):
        return {}

    async def job_get(_session, _key):
        return {"event_end": "2026-10-01T00:00:00+00:00", "ranks_a": [], "ranks_b": []}

    monkeypatch.setattr(season, "get_settings", get_settings)
    monkeypatch.setattr(season, "event_bounds", lambda _cfg: (end - timedelta(days=14), end))
    monkeypatch.setattr(season, "job_get", job_get)
    session = FakeSession()
    assert await season.finalize_season(session, end) is None
    assert session.added == 0
