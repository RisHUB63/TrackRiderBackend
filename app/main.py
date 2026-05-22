from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.room import router as room_router
from app.api.ws import router as ws_router
from app.core.config import settings
from app.core.database import engine, Base
from app.models.user import User  # noqa: F401
from app.models.room import Room, RoomMember  # noqa: F401

app = FastAPI(
    title=settings.app_name,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)


@app.on_event("startup")
async def on_startup():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception:
        pass  # Tables likely already exist in production


app.include_router(auth_router, prefix="/api/v1")
app.include_router(room_router, prefix="/api/v1")
app.include_router(ws_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/")
async def working():
    return {"status": "OK", "message": "Welcome to the TrackRider Backend"}
