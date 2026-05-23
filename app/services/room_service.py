import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.room import Room, RoomMember


class RoomServiceError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code


class RoomService:
    def __init__(self, session: AsyncSession):
        self._session = session

    def _generate_code(self) -> str:
        return secrets.token_urlsafe(6)[:8].upper()

    async def create_room(self, name: str, room_type: str, created_by: str, max_members: int | None) -> Room:
        # Check if user is already in a room
        existing = await self._get_user_membership(created_by)
        if existing:
            raise RoomServiceError("You are already in a room. Leave it first.", status_code=409)

        code = self._generate_code()
        room = Room(
            id=str(uuid.uuid4()),
            name=name,
            code=code,
            type=room_type,
            max_members=max_members,
            created_by=created_by,
        )
        self._session.add(room)

        # Creator auto-joins the room
        member = RoomMember(
            id=str(uuid.uuid4()),
            room_id=room.id,
            user_id=created_by,
        )
        self._session.add(member)
        await self._session.commit()
        await self._session.refresh(room)
        return room

    async def join_room(self, code: str, user_id: str) -> Room:
        room = await self._get_room_by_code(code)
        if not room:
            raise RoomServiceError("Room not found", status_code=404)
        if not room.is_active:
            raise RoomServiceError("Room is no longer active", status_code=410)

        # If user is already in this room (as member or creator), let them back in
        existing = await self._get_user_membership(user_id)
        if existing:
            if existing.room_id == room.id:
                return room
            raise RoomServiceError("You are already in a different room. Leave it first.", status_code=409)

        # Check max members
        if room.max_members is not None:
            count = await self._get_member_count(room.id)
            if count >= room.max_members:
                raise RoomServiceError("Room is full", status_code=403)

        member = RoomMember(
            id=str(uuid.uuid4()),
            room_id=room.id,
            user_id=user_id,
        )
        self._session.add(member)
        await self._session.commit()
        await self._session.refresh(room)
        return room

    async def leave_room(self, user_id: str) -> None:
        membership = await self._get_user_membership(user_id)
        if not membership:
            raise RoomServiceError("You are not in any room", status_code=404)

        await self._session.delete(membership)
        await self._session.commit()

    async def get_my_room(self, user_id: str) -> Room | None:
        membership = await self._get_user_membership(user_id)
        if not membership:
            return None
        result = await self._session.execute(select(Room).where(Room.id == membership.room_id))
        return result.scalar_one_or_none()

    async def get_room_members(self, room_id: str, user_id: str) -> list[dict]:
        # Validate user is in this room
        membership = await self._get_user_membership(user_id)
        if not membership or membership.room_id != room_id:
            raise RoomServiceError("You are not a member of this room", status_code=403)

        from app.models.user import User
        result = await self._session.execute(
            select(RoomMember, User.email)
            .join(User, RoomMember.user_id == User.id)
            .where(RoomMember.room_id == room_id)
        )
        rows = result.all()
        return [
            {"id": m.id, "user_id": m.user_id, "email": email, "joined_at": m.joined_at}
            for m, email in rows
        ]

    async def get_member_count(self, room_id: str) -> int:
        return await self._get_member_count(room_id)

    async def _get_room_by_code(self, code: str) -> Room | None:
        result = await self._session.execute(select(Room).where(Room.code == code))
        return result.scalar_one_or_none()

    async def _get_user_membership(self, user_id: str) -> RoomMember | None:
        result = await self._session.execute(
            select(RoomMember).where(RoomMember.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def _get_member_count(self, room_id: str) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(RoomMember).where(RoomMember.room_id == room_id)
        )
        return result.scalar_one()
