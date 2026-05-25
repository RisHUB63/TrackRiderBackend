import secrets
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.room import Room, RoomMember
from app.models.user import User

log = get_logger("rooms")


class RoomServiceError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code


class RoomService:
    def __init__(self, session: AsyncSession):
        self._session = session

    def _generate_code(self) -> str:
        return secrets.token_urlsafe(6)[:8].upper()

    async def _get_creator_username(self, room: Room) -> str:
        result = await self._session.execute(
            select(User.username).where(User.id == room.created_by)
        )
        username = result.scalar_one_or_none()
        return username or ""

    async def build_room_response(self, room: Room) -> dict:
        """Shape a Room into the API response payload (no UUID exposed)."""
        count = await self._get_member_count(room.id)
        creator_username = await self._get_creator_username(room)
        return {
            "name": room.name,
            "code": room.code,
            "type": room.type,
            "max_members": room.max_members,
            "is_active": room.is_active,
            "created_by": creator_username,
            "created_at": room.created_at,
            "member_count": count,
        }

    async def create_room(
        self, name: str, room_type: str, created_by: str, max_members: int | None
    ) -> Room:
        # Check if user is already in an active room
        existing = await self._get_active_membership(created_by)
        if existing:
            raise RoomServiceError(
                "You are already in a room. Exit it first.", status_code=409
            )

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
        log.info(
            "room created code=%s type=%s creator=%s", room.code, room.type, created_by
        )
        return room

    async def join_room(self, code: str, user_id: str) -> Room:
        room = await self._get_room_by_code(code)
        if not room:
            raise RoomServiceError("Room not found", status_code=404)
        if not room.is_active:
            raise RoomServiceError("Room is no longer available", status_code=410)

        # If user is already in this room, let them back in
        existing = await self._get_active_membership(user_id)
        if existing:
            if existing.room_id == room.id:
                return room
            raise RoomServiceError(
                "You are already in a different room. Exit it first.",
                status_code=409,
            )

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
        log.info("room join ok code=%s user=%s", room.code, user_id)
        return room

    async def exit_room(self, code: str, user_id: str) -> Room:
        """
        Only the room creator can exit (end) a room. Doing so deactivates the
        room so no one can rejoin and clears all memberships.
        """
        room = await self._get_room_by_code(code)
        if not room:
            raise RoomServiceError("Room not found", status_code=404)
        if room.created_by != user_id:
            raise RoomServiceError(
                "Only the room creator can exit this room", status_code=403
            )
        if not room.is_active:
            raise RoomServiceError("Room is already closed", status_code=410)

        room.is_active = False
        await self._session.execute(
            delete(RoomMember).where(RoomMember.room_id == room.id)
        )
        await self._session.commit()
        await self._session.refresh(room)
        log.info("room exited code=%s creator=%s", room.code, user_id)
        return room

    async def get_my_room(self, user_id: str) -> Room | None:
        membership = await self._get_active_membership(user_id)
        if not membership:
            return None
        result = await self._session.execute(
            select(Room).where(Room.id == membership.room_id)
        )
        return result.scalar_one_or_none()

    async def get_room_members_by_code(self, code: str, user_id: str) -> list[dict]:
        room = await self._get_room_by_code(code)
        if not room:
            raise RoomServiceError("Room not found", status_code=404)
        if not room.is_active:
            raise RoomServiceError("Room is no longer available", status_code=410)

        # Validate caller is in this room
        membership = await self._get_active_membership(user_id)
        if not membership or membership.room_id != room.id:
            raise RoomServiceError(
                "You are not a member of this room", status_code=403
            )

        admin_id = room.created_by
        result = await self._session.execute(
            select(User.username, RoomMember.joined_at, RoomMember.user_id)
            .join(User, RoomMember.user_id == User.id)
            .where(RoomMember.room_id == room.id)
            .order_by(RoomMember.joined_at.asc())
        )
        rows = result.all()
        return [
            {
                "username": username,
                "joined_at": joined_at,
                "status": "admin" if uid == admin_id else "member",
            }
            for username, joined_at, uid in rows
        ]

    async def get_member_count(self, room_id: str) -> int:
        return await self._get_member_count(room_id)

    async def get_room_by_code(self, code: str) -> Room | None:
        return await self._get_room_by_code(code)

    async def _get_room_by_code(self, code: str) -> Room | None:
        normalized = code.strip().upper()
        result = await self._session.execute(
            select(Room).where(Room.code == normalized)
        )
        return result.scalar_one_or_none()

    async def _get_active_membership(self, user_id: str) -> RoomMember | None:
        """Return the user's membership only if the underlying room is still active."""
        result = await self._session.execute(
            select(RoomMember)
            .join(Room, Room.id == RoomMember.room_id)
            .where(RoomMember.user_id == user_id, Room.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def _get_member_count(self, room_id: str) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(RoomMember)
            .where(RoomMember.room_id == room_id)
        )
        return result.scalar_one()
