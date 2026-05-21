from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import (
    TokenPair,
    TokenRefresh,
    UserLogin,
    UserResponse,
    UserSignup,
    WsTokenResponse,
)
from app.services.auth_service import AuthService, AuthServiceError

router = APIRouter(prefix="/auth", tags=["auth"])
bearer_scheme = HTTPBearer()


@router.post("/signup", response_model=UserResponse, status_code=201)
async def signup(body: UserSignup, session: AsyncSession = Depends(get_db)):
    try:
        service = AuthService(session)
        user = await service.signup(email=body.email, password=body.password)
        return user
    except AuthServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/login", response_model=TokenPair)
async def login(body: UserLogin, session: AsyncSession = Depends(get_db)):
    try:
        service = AuthService(session)
        return await service.login(email=body.email, password=body.password)
    except AuthServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: TokenRefresh, session: AsyncSession = Depends(get_db)):
    try:
        service = AuthService(session)
        return await service.refresh_tokens(refresh_token=body.refresh_token)
    except AuthServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/logout", status_code=204)
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
):
    try:
        service = AuthService(session)
        await service.logout(access_token=credentials.credentials)
    except AuthServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/ws-token", response_model=WsTokenResponse)
async def ws_token(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = AuthService(session)
    return await service.issue_ws_token(user_id=str(current_user.id))
