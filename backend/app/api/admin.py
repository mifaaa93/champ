from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.schemas import SettingsPatch
from app.services.freeze import freeze_day
from app.services.poll import refresh_statistics, snapshot_watchlist
from app.settings_service import get_settings, update_settings
from app.timezone import dubai_today

router = APIRouter(prefix="/admin")


async def require_admin(x_admin_token: str = Header(default="")) -> None:
    if not x_admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="bad admin token")


@router.get("/settings", dependencies=[Depends(require_admin)])
async def read_settings(session: AsyncSession = Depends(get_session)) -> dict:
    return await get_settings(session)


@router.patch("/settings", dependencies=[Depends(require_admin)])
async def patch_settings(
    body: SettingsPatch, session: AsyncSession = Depends(get_session)
) -> dict:
    patch = body.model_dump(exclude_none=True)
    return await update_settings(session, patch)


@router.post("/snapshot", dependencies=[Depends(require_admin)])
async def run_snapshot(session: AsyncSession = Depends(get_session)) -> dict:
    stats = await refresh_statistics(session)
    snaps = await snapshot_watchlist(session)
    return {"stats": stats, "snapshots": snaps}


@router.post("/day-close", dependencies=[Depends(require_admin)])
async def day_close(session: AsyncSession = Depends(get_session)) -> dict:
    return await freeze_day(session, dubai_today())
