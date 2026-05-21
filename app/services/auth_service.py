from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_ws_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.redis import blacklist_token, is_token_blacklisted
from app.schemas.auth import TokenPair, WsTokenResponse
from app.services.user_repository import UserRepository


class AuthServiceError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code


class AuthService:
    def __init__(self, session: AsyncSession):
        self._repo = UserRepository(session)

    async def signup(self, email: str, password: str):
        if await self._repo.exists_by_email(email):
            raise AuthServiceError("Email already registered", status_code=409)

        hashed = hash_password(password)
        return await self._repo.create(email=email, hashed_password=hashed)

    async def login(self, email: str, password: str) -> TokenPair:
        user = await self._repo.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise AuthServiceError("Invalid credentials", status_code=401)

        if not user.is_active:
            raise AuthServiceError("Account is deactivated", status_code=403)

        user_id = str(user.id)
        return TokenPair(
            access_token=create_access_token(user_id),
            refresh_token=create_refresh_token(user_id),
        )

    async def refresh_tokens(self, refresh_token: str) -> TokenPair:
        if await is_token_blacklisted(refresh_token):
            raise AuthServiceError("Token has been revoked", status_code=401)

        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise AuthServiceError("Invalid refresh token", status_code=401)

        user_id = payload["sub"]
        user = await self._repo.get_by_id(user_id)
        if not user or not user.is_active:
            raise AuthServiceError("User not found or inactive", status_code=401)

        from app.core.config import settings
        ttl = settings.refresh_token_expire_days * 86400
        await blacklist_token(refresh_token, ttl)

        return TokenPair(
            access_token=create_access_token(user_id),
            refresh_token=create_refresh_token(user_id),
        )

    async def logout(self, access_token: str, refresh_token: str | None = None) -> None:
        from app.core.config import settings

        await blacklist_token(access_token, settings.access_token_expire_minutes * 60)
        if refresh_token:
            await blacklist_token(refresh_token, settings.refresh_token_expire_days * 86400)

    async def issue_ws_token(self, user_id: str) -> WsTokenResponse:
        from app.core.config import settings

        token = create_ws_token(user_id)
        return WsTokenResponse(
            ws_token=token,
            expires_in_seconds=settings.ws_token_expire_minutes * 60,
        )
