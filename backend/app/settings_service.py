from copy import deepcopy

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSetting

from app.telegram import DEFAULT_TEMPLATES

DEFAULTS: dict = {
    "timezone": "Africa/Johannesburg",
    "top_n": 7,
    "min_day_deposit": 50,
    "publish_interval_minutes": 60,
    "min_return_pct": 0,
    "prize_yield": [100, 50, 25],
    "prize_loss_pct": [15, 10, 5],
    "loss_comp_cap": 500,
    "require_trade": False,
    "prize_places": 3,
    "event_name": "PO TOURNAMENT",
    "event_end": "",
    "prize_pool": 5000,
    "prize_table": [
        {"place": "1 место", "amount": 1500, "suffix": ""},
        {"place": "2 место", "amount": 1000, "suffix": ""},
        {"place": "3 место", "amount": 700, "suffix": ""},
        {"place": "4 место", "amount": 500, "suffix": ""},
        {"place": "5 место", "amount": 400, "suffix": ""},
        {"place": "6–10 места", "amount": 180, "suffix": "каждое"},
    ],
    "stats_players": 14502,
    "stats_turnover": 2_400_000,
    "telegram_channel_url": "https://t.me/your_channel",
    "rami_url": "https://t.me/rami_username",
    "event_rules": [
        "Турнир открыт для участников команды.",
        "Рейтинг формируется по сумме депозитов за период турнира.",
        "Оборот учитывается за последние 30 дней активности, если данные есть в базе.",
        "Топ-10 витрины и призовой фонд задаются в админке.",
        "Результаты обновляются по снимкам счёта.",
        "В случае споров решение организатора является окончательным.",
    ],
    "activity": [
        {"name": "Александр", "action": "поднялся на", "rank": 42, "extra": "", "time": "2 мин назад"},
        {"name": "Дмитрий", "action": "пополнил депозит на", "rank": None, "extra": "$500", "time": "5 мин назад"},
        {"name": "Максим", "action": "вошёл в Топ-100", "rank": 87, "extra": "", "time": "12 мин назад"},
        {"name": "Сергей", "action": "обогнал", "rank": None, "extra": "12 трейдеров", "time": "18 мин назад"},
        {"name": "Андрей", "action": "достиг оборота", "rank": None, "extra": "$50,000", "time": "25 мин назад"},
    ],
    **DEFAULT_TEMPLATES,
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
    changed = False
    if merged.get("timezone") != "Africa/Johannesburg":
        merged["timezone"] = "Africa/Johannesburg"
        changed = True
    for key, value in list(merged.items()):
        if isinstance(value, str) and "Dubai" in value:
            merged[key] = value.replace("Asia/Dubai", "UTC+2").replace("Dubai", "UTC+2")
            changed = True
    if not str(merged.get("event_end") or "").strip():
        from datetime import timedelta

        from app.timezone import now_champ

        merged["event_end"] = (now_champ() + timedelta(days=14)).isoformat()
        changed = True
    if changed:
        row.value = merged
        await session.commit()
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
