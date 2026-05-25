from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
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

log = get_logger("auth")


class AuthServiceError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code


class AuthService:
    def __init__(self, session: AsyncSession):
        self._repo = UserRepository(session)

    async def signup(self, email: str, username: str, password: str):
        if await self._repo.exists_by_email(email):
            log.info("signup rejected: email taken (%s)", email)
            raise AuthServiceError("Email already registered", status_code=409)
        if await self._repo.exists_by_username(username):
            log.info("signup rejected: username taken (%s)", username)
            raise AuthServiceError("Username already taken", status_code=409)

        hashed = hash_password(password)
        user = await self._repo.create(
            email=email, username=username, hashed_password=hashed
        )
        log.info("signup ok user_id=%s username=%s", user.id, user.username)
        return user

    async def login(self, identifier: str, password: str) -> TokenPair:
        user = await self._repo.get_by_identifier(identifier)
        if not user or not verify_password(password, user.hashed_password):
            log.info("login failed for identifier=%s", identifier)
            raise AuthServiceError("Invalid credentials", status_code=401)

        if not user.is_active:
            log.warning("login blocked, inactive user_id=%s", user.id)
            raise AuthServiceError("Account is deactivated", status_code=403)

        log.info("login ok user_id=%s", user.id)
        user_id = str(user.id)
        return TokenPair(
            access_token=create_access_token(user_id),
            refresh_token=create_refresh_token(user_id),
        )

    async def refresh_tokens(self, refresh_token: str) -> TokenPair:
        if await is_token_blacklisted(refresh_token):
            log.info("refresh rejected: token blacklisted")
            raise AuthServiceError("Token has been revoked", status_code=401)

        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            log.info("refresh rejected: invalid payload")
            raise AuthServiceError("Invalid refresh token", status_code=401)

        user_id = payload["sub"]
        user = await self._repo.get_by_id(user_id)
        if not user or not user.is_active:
            log.warning("refresh rejected: user missing/inactive user_id=%s", user_id)
            raise AuthServiceError("User not found or inactive", status_code=401)

        from app.core.config import settings
        ttl = settings.refresh_token_expire_days * 86400
        await blacklist_token(refresh_token, ttl)

        log.info("refresh ok user_id=%s", user_id)
        return TokenPair(
            access_token=create_access_token(user_id),
            refresh_token=create_refresh_token(user_id),
        )

    async def logout(self, access_token: str, refresh_token: str | None = None) -> None:
        from app.core.config import settings

        await blacklist_token(access_token, settings.access_token_expire_minutes * 60)
        if refresh_token:
            await blacklist_token(refresh_token, settings.refresh_token_expire_days * 86400)
        log.info("logout ok")

    async def issue_ws_token(self, user_id: str) -> WsTokenResponse:
        from app.core.config import settings

        token = create_ws_token(user_id)
        log.debug("issued ws-token user_id=%s", user_id)
        return WsTokenResponse(
            ws_token=token,
            expires_in_seconds=settings.ws_token_expire_minutes * 60,
        )
