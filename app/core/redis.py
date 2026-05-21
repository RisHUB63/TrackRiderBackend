import redis.asyncio as redis

from app.core.config import settings

redis_client = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
    decode_responses=True,
)


async def blacklist_token(token: str, expires_in: int) -> None:
    """Add a token to the blacklist with TTL matching its expiry."""
    await redis_client.setex(f"blacklist:{token}", expires_in, "1")


async def is_token_blacklisted(token: str) -> bool:
    """Check if a token has been revoked."""
    return await redis_client.exists(f"blacklist:{token}") > 0
