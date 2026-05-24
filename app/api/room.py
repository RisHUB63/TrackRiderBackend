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
        count = await service.get_member_count(room.id)
        return RoomResponse(
            id=room.id,
            name=room.name,
            code=room.code,
            type=room.type,
            max_members=room.max_members,
            is_active=room.is_active,
            created_by=room.created_by,
            created_at=room.created_at,
            member_count=count,
        )
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
        count = await service.get_member_count(room.id)
        return RoomResponse(
            id=room.id,
            name=room.name,
            code=room.code,
            type=room.type,
            max_members=room.max_members,
            is_active=room.is_active,
            created_by=room.created_by,
            created_at=room.created_at,
            member_count=count,
        )
    except RoomServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/leave", status_code=204)
async def leave_room(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        service = RoomService(session)
        await service.leave_room(user_id=current_user.id)
    except RoomServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/{room_id}/close", status_code=204)
async def close_room(
    room_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        service = RoomService(session)
        await service.close_room(room_id=room_id, user_id=current_user.id)
    except RoomServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    # Notify and disconnect any active WS clients in this room
    await manager.close_room(room_id)


@router.get("/me", response_model=RoomResponse | None)
async def my_room(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    service = RoomService(session)
    room = await service.get_my_room(user_id=current_user.id)
    if not room:
        return None
    count = await service.get_member_count(room.id)
    return RoomResponse(
        id=room.id,
        name=room.name,
        code=room.code,
        type=room.type,
        max_members=room.max_members,
        is_active=room.is_active,
        created_by=room.created_by,
        created_at=room.created_at,
        member_count=count,
    )


@router.get("/{room_id}/members", response_model=list[RoomMemberResponse])
async def room_members(
    room_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        service = RoomService(session)
        members = await service.get_room_members(room_id=room_id, user_id=current_user.id)
        return members
    except RoomServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
