import asyncio
import logging

from app.config import settings
from app.db import init_db
from app.jobs.runner import build_scheduler, job_snapshots, job_statistics, recover
from app.settings_service import get_settings
from app.db import SessionLocal

logging.basicConfig(level=settings.log_level)
log = logging.getLogger("champ.worker")


async def main() -> None:
    await init_db()
    async with SessionLocal() as session:
        await get_settings(session)
    await recover()
    try:
        await job_statistics()
        await job_snapshots()
    except Exception:
        log.exception("initial poll failed")
    scheduler = build_scheduler()
    scheduler.start()
    log.info("worker started")
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
