"""
Lightweight idempotent schema migrations.

Run on startup, only applies changes that are missing. Safe to call repeatedly.
Each step logs its outcome so failures are visible in Vercel logs.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.logging import get_logger

log = get_logger("migrations")


async def _run_step(conn, name: str, sql: str) -> None:
    try:
        await conn.execute(text(sql))
        log.info("migration step ok: %s", name)
    except Exception:
        log.exception("migration step failed: %s", name)
        raise


async def apply_migrations(engine: AsyncEngine) -> None:
    log.info("Applying migrations")
    async with engine.begin() as conn:
        await _run_step(
            conn,
            "users.username add column",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(50)",
        )

        await _run_step(
            conn,
            "users.username backfill",
            """
            UPDATE users
            SET username = LEFT(
                REGEXP_REPLACE(SPLIT_PART(email, '@', 1), '[^A-Za-z0-9_.-]', '_', 'g'),
                40
            ) || '_' || LEFT(REPLACE(id::text, '-', ''), 6)
            WHERE username IS NULL
            """,
        )

        await _run_step(
            conn,
            "users.username set not null",
            "ALTER TABLE users ALTER COLUMN username SET NOT NULL",
        )

        await _run_step(
            conn,
            "users.username unique index",
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)",
        )

    log.info("Migrations finished")
