import ssl

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

connect_args = {}
db_url = settings.db_url

# Enable SSL for production PostgreSQL (Neon, Supabase, etc.)
if "sslmode=require" in (settings.database_url or ""):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    connect_args["ssl"] = ssl_context
    # Remove sslmode from URL since asyncpg handles it via connect_args
    db_url = db_url.split("?")[0]

engine = create_async_engine(db_url, echo=settings.debug, connect_args=connect_args)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass
