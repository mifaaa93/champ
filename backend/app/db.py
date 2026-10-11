from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import Base

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in (
            "ALTER TABLE showcase_leads ADD COLUMN IF NOT EXISTS randomize BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE showcase_leads ADD COLUMN IF NOT EXISTS balance NUMERIC(18, 4) NOT NULL DEFAULT 0",
            "ALTER TABLE showcase_leads ADD COLUMN IF NOT EXISTS pnl NUMERIC(18, 4) NOT NULL DEFAULT 0",
            "ALTER TABLE showcase_leads ADD COLUMN IF NOT EXISTS return_pct NUMERIC(18, 6) NOT NULL DEFAULT 0",
        ):
            await conn.execute(text(stmt))
