import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Participant
from app.partners import partners_client


async def register_participant(
    session: AsyncSession, uid: int, nickname: str = "", telegram: str = ""
) -> Participant:
    existing = (
        await session.execute(select(Participant).where(Participant.uid == uid))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Этот UID уже зарегистрирован")

    try:
        info = await partners_client.user_info(uid)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Partners API недоступен") from exc
    if not info:
        raise HTTPException(
            status_code=404,
            detail="UID не найден в нашем партнёрском контуре Pocket Option",
        )

    nick = (nickname or "").strip()[:64]
    tg = (telegram or "").strip().lstrip("@")[:64]
    part = Participant(
        uid=uid,
        nickname=nick,
        telegram=tg,
        country=info.get("country"),
    )
    session.add(part)
    await session.commit()
    await session.refresh(part)
    return part
