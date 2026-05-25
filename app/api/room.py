from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.room import (
    CreateRoomRequest,
    JoinRoomRequest,
    RoomMemberResponse,
    RoomResponse,
)
from app.services.room_service import RoomService, RoomServiceError
from app.services.ws_manager import manager

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.post("", response_model=RoomResponse, status_code=201)
async def create_room(
    body: CreateRoomRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        service = RoomService(session)
        room = await service.create_room(
            name=body.name,
            room_type=body.type.value,
            created_by=current_user.id,
            max_members=body.max_members,
        )
        return await service.build_room_response(room)
    except RoomServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/join", response_model=RoomResponse)
async def join_room(
    body: JoinRoomRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        service = RoomService(session)
        room = await service.join_room(code=body.code, user_id=current_user.id)
        return await service.build_room_response(room)
    except RoomServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/{code}/exit", status_code=204)
async def exit_room(
    code: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Creator-only: ends the room. After this, the room is no longer available
    and no one can rejoin it.
    """
    try:
        service = RoomService(session)
        room = await service.exit_room(
            code=code.strip().upper(), user_id=current_user.id
        )
    except RoomServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    # Notify and disconnect any active WS clients in this room
    await manager.close_room(room.id)


@router.get("/me", response_model=RoomResponse | None)
async def my_room(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = RoomService(session)
    room = await service.get_my_room(user_id=current_user.id)
    if not room:
        return None
    return await service.build_room_response(room)


@router.get("/{code}/members", response_model=list[RoomMemberResponse])
async def room_members(
    code: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        service = RoomService(session)
        return await service.get_room_members_by_code(
            code=code.strip().upper(), user_id=current_user.id
        )
    except RoomServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
