import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.admin import router as admin_router
from app.api.public import router as public_router
from app.config import settings
from app.db import init_db
from app.settings_service import get_settings
from app.db import SessionLocal

logging.basicConfig(level=settings.log_level)
log = logging.getLogger("champ.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    async with SessionLocal() as session:
        await get_settings(session)
    log.info("api up v%s", __version__)
    yield


app = FastAPI(title="Championship API", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(public_router)
app.include_router(admin_router)


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "version": __version__}
