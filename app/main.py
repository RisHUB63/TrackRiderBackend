from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.room import router as room_router
from app.api.ws import router as ws_router
from app.core.config import settings
from app.core.database import engine, Base
from app.core.logging import get_logger, setup_logging
from app.core.migrations import apply_migrations
from app.models.user import User  # noqa: F401
from app.models.room import Room, RoomMember  # noqa: F401

setup_logging("DEBUG" if settings.debug else "INFO")
log = get_logger("app")

app = FastAPI(
    title=settings.app_name,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_VERSION = "/api/v1"


@app.on_event("startup")
async def on_startup():
    log.info("Starting %s (debug=%s)", settings.app_name, settings.debug)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("Schema bootstrap complete (create_all)")
    except Exception:
        # Tables likely already exist; log but don't crash boot.
        log.exception("create_all failed; continuing")

    try:
        await apply_migrations(engine)
        log.info("Migrations applied successfully")
    except Exception:
        log.exception("Migration step failed")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    # Re-raise so FastAPI's default handler still produces a 500 response
    raise exc


app.include_router(auth_router, prefix=API_VERSION)
app.include_router(room_router, prefix=API_VERSION)
app.include_router(ws_router, prefix=API_VERSION)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/")
async def working():
    return {"status": "OK", "message": "Welcome to the TrackRider Backend"}
