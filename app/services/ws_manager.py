"""
WebSocket Connection Manager

Handles:
- Active connection tracking per user
- Socket room management (join/leave/broadcast)
- Heartbeat/ping-pong for connection health
- Graceful disconnect and cleanup
"""

import asyncio
import time
from dataclasses import dataclass, field

from fastapi import WebSocket

from app.core.config import settings

HEARTBEAT_INTERVAL = settings.ws_heartbeat_interval
HEARTBEAT_TIMEOUT = settings.ws_heartbeat_timeout


@dataclass
class Connection:
    websocket: WebSocket
    user_id: str
    room_id: str | None = None
    last_pong: float = field(default_factory=time.time)
    connected_at: float = field(default_factory=time.time)


class ConnectionManager:
    """Manages all active WebSocket connections, rooms, and heartbeats."""

    def __init__(self):
        # user_id -> Connection
        self._connections: dict[str, Connection] = {}
        # room_id -> set of user_ids
        self._rooms: dict[str, set[str]] = {}
        # Background heartbeat task
        self._heartbeat_task: asyncio.Task | None = None

    @property
    def active_connections(self) -> int:
        return len(self._connections)

    # ─── Connection Lifecycle ────────────────────────────────────────────

    async def connect(self, websocket: WebSocket, user_id: str) -> Connection:
        """Register a new connection. Disconnects previous session if exists."""
        # If user already connected, close old connection (handles reconnect)
        if user_id in self._connections:
            await self.disconnect(user_id, code=4001, reason="new_session")

        conn = Connection(websocket=websocket, user_id=user_id)
        self._connections[user_id] = conn

        # Start heartbeat loop if not running
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        return conn

    async def disconnect(self, user_id: str, code: int = 1000, reason: str = "normal") -> None:
        """Remove connection and clean up room membership."""
        conn = self._connections.pop(user_id, None)
        if not conn:
            return

        # Remove from room
        if conn.room_id:
            await self._leave_room(user_id, conn.room_id, notify=True)

        # Close the websocket gracefully
        try:
            await conn.websocket.close(code=code, reason=reason)
        except Exception:
            pass

    def get_connection(self, user_id: str) -> Connection | None:
        return self._connections.get(user_id)

    def is_connected(self, user_id: str) -> bool:
        return user_id in self._connections

    # ─── Room Management ─────────────────────────────────────────────────

    async def join_room(self, user_id: str, room_id) -> None:
        """Add user to a socket room and notify other members."""
        conn = self._connections.get(user_id)
        if not conn:
            return

        # Leave current room first if in one
        if conn.room_id and conn.room_id != room_id:
            await self._leave_room(user_id, conn.room_id, notify=True)

        conn.room_id = room_id
        if room_id not in self._rooms:
            self._rooms[room_id] = set()
        self._rooms[room_id].add(user_id)

        # Notify room members
        await self.broadcast_to_room(
            room_id,
            {"type": "member_joined", "user_id": user_id},
            exclude=user_id,
        )

        # Confirm to the user
        await self.send_to_user(user_id, {
            "type": "room_joined",
            "room_id": room_id,
            "members": list(self._rooms[room_id]),
        })

    async def leave_room(self, user_id: str) -> None:
        """Remove user from their current room."""
        conn = self._connections.get(user_id)
        if not conn or not conn.room_id:
            return
        await self._leave_room(user_id, conn.room_id, notify=True)
        conn.room_id = None

    async def _leave_room(self, user_id: str, room_id: str, notify: bool = False) -> None:
        """Internal: remove user from room set and optionally notify."""
        room_members = self._rooms.get(room_id)
        if not room_members:
            return

        room_members.discard(user_id)

        if notify and room_members:
            await self.broadcast_to_room(
                room_id,
                {"type": "member_left", "user_id": user_id},
            )

        # Clean up empty rooms
        if not room_members:
            del self._rooms[room_id]

    def get_room_members(self, room_id: str) -> set[str]:
        return self._rooms.get(room_id, set())

    # ─── Messaging ───────────────────────────────────────────────────────

    async def send_to_user(self, user_id: str, data: dict) -> None:
        """Send JSON message to a specific user."""
        conn = self._connections.get(user_id)
        if conn:
            try:
                await conn.websocket.send_json(data)
            except Exception:
                await self.disconnect(user_id, code=1011, reason="send_error")

    async def broadcast_to_room(self, room_id: str, data: dict, exclude: str | None = None) -> None:
        """Send JSON message to all members of a room."""
        members = self._rooms.get(room_id, set())
        for uid in list(members):
            if uid == exclude:
                continue
            await self.send_to_user(uid, data)

    async def broadcast_all(self, data: dict) -> None:
        """Send JSON message to all connected users."""
        for uid in list(self._connections.keys()):
            await self.send_to_user(uid, data)

    # ─── Heartbeat / Ping-Pong ───────────────────────────────────────────

    async def handle_pong(self, user_id: str) -> None:
        """Update last_pong timestamp when client responds to ping."""
        conn = self._connections.get(user_id)
        if conn:
            conn.last_pong = time.time()

    async def _heartbeat_loop(self) -> None:
        """Periodically ping all connections and drop unresponsive ones."""
        while self._connections:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            now = time.time()
            stale_users = []

            for user_id, conn in list(self._connections.items()):
                # Check if last pong is too old
                if now - conn.last_pong > HEARTBEAT_INTERVAL + HEARTBEAT_TIMEOUT:
                    stale_users.append(user_id)
                else:
                    # Send ping
                    try:
                        await conn.websocket.send_json({"type": "ping", "ts": now})
                    except Exception:
                        stale_users.append(user_id)

            # Disconnect stale connections
            for user_id in stale_users:
                await self.disconnect(user_id, code=1001, reason="heartbeat_timeout")


# Singleton instance
manager = ConnectionManager()
