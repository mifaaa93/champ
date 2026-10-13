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
            "ALTER TABLE showcase_leads ADD COLUMN IF NOT EXISTS board VARCHAR(1) NOT NULL DEFAULT 'A'",
            "ALTER TABLE day_results ADD COLUMN IF NOT EXISTS card JSONB",
        ):
            await conn.execute(text(stmt))
        await conn.execute(
            text(
                """
                DO $$
                DECLARE
                  cols text;
                BEGIN
                  SELECT string_agg(a.attname, ',' ORDER BY k.ord)
                  INTO cols
                  FROM pg_constraint c
                  JOIN pg_class t ON t.oid = c.conrelid
                  JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON true
                  JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
                  WHERE t.relname = 'showcase_leads' AND c.contype = 'p';
                  IF cols IS DISTINCT FROM 'board,place' THEN
                    ALTER TABLE showcase_leads DROP CONSTRAINT IF EXISTS showcase_leads_pkey;
                    ALTER TABLE showcase_leads ADD PRIMARY KEY (board, place);
                  END IF;
                EXCEPTION
                  WHEN duplicate_object THEN
                    NULL;
                END $$;
                """
            )
        )
