import redis.asyncio as redis

from app.core.config import settings

redis_client: redis.Redis | None = None

try:
    if settings.redis_url:
        redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    else:
        redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True,
        )
except Exception:
    redis_client = None


async def blacklist_token(token: str, expires_in: int) -> None:
    """Add a token to the blacklist with TTL matching its expiry."""
    if redis_client:
        try:
            await redis_client.setex(f"blacklist:{token}", expires_in, "1")
        except Exception:
            pass


async def is_token_blacklisted(token: str) -> bool:
    """Check if a token has been revoked."""
    if redis_client:
        try:
            return await redis_client.exists(f"blacklist:{token}") > 0
        except Exception:
            return False
    return False
