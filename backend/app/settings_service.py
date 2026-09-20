from copy import deepcopy

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSetting

DEFAULTS: dict = {
    "timezone": "Asia/Dubai",
    "top_n": 7,
    "min_day_deposit": 50,
    "publish_interval_minutes": 60,
    "prize_yield": [100, 50, 25],
    "prize_loss_pct": [15, 10, 5],
    "loss_comp_cap": 500,
    "require_trade": False,
    "prize_places": 3,
}

SETTINGS_KEY = "championship"


async def get_settings(session: AsyncSession) -> dict:
    row = await session.get(AppSetting, SETTINGS_KEY)
    if row is None:
        row = AppSetting(key=SETTINGS_KEY, value=deepcopy(DEFAULTS))
        session.add(row)
        await session.commit()
        await session.refresh(row)
    merged = deepcopy(DEFAULTS)
    merged.update(row.value or {})
    return merged


async def update_settings(session: AsyncSession, patch: dict) -> dict:
    current = await get_settings(session)
    for key, value in patch.items():
        if key not in DEFAULTS:
            continue
        current[key] = value
    row = await session.get(AppSetting, SETTINGS_KEY)
    if row is None:
        row = AppSetting(key=SETTINGS_KEY, value=current)
        session.add(row)
    else:
        row.value = current
    await session.commit()
    return current


async def job_get(session: AsyncSession, key: str) -> dict:
    from app.models import JobState

    row = await session.get(JobState, key)
    return dict(row.value) if row else {}


async def job_set(session: AsyncSession, key: str, value: dict) -> None:
    from app.models import JobState

    row = await session.get(JobState, key)
    if row is None:
        session.add(JobState(key=key, value=value))
    else:
        row.value = value
    await session.commit()
