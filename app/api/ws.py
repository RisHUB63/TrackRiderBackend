"""
WebSocket API Endpoint

Connection:
  ws://host/api/v1/ws?token=<ws_token>&room_id=<room_id>

The client connects with both a token and a room_id. Authentication and
room assignment happen at connection time — no separate join step needed.

Message Types (client -> server):
  {"type": "pong"}                                    - Heartbeat response
  {"type": "location", "lat": ..., "lng": ..., ...}  - Share location
  {"type": "message", "text": "..."}                  - Send text to room

Message Types (server -> client):
  {"type": "ping", "ts": ...}                         - Heartbeat ping
  {"type": "connected", "user_id": ..., "room_id": ..., "members": [...]}
  {"type": "member_joined", "user_id": ...}
  {"type": "member_left", "user_id": ...}
  {"type": "location", "user_id": ..., "lat": ..., "lng": ..., ...}
  {"type": "message", "user_id": ..., "text": ...}
  {"type": "error", "detail": "..."}
"""

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.database import async_session_factory
from app.core.security import decode_token
from app.services.room_service import RoomService
from app.services.user_repository import UserRepository
from app.services.ws_manager import manager

router = APIRouter(tags=["websocket"])


async def authenticate_ws(websocket: WebSocket) -> tuple[str | None, str | None]:
    """Validate WS token and room_id. Returns (user_id, room_id) or (None, None)."""
    token = websocket.query_params.get("token")
    room_id = websocket.query_params.get("room_id")

    if not token or not room_id:
        return None, None

    payload = decode_token(token)
    if not payload or payload.get("type") != "ws":
        return None, None

    user_id = payload.get("sub")
    if not user_id:
        return None, None

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if not user or not user.is_active:
            return None, None

        # Verify user is actually a member of this room
        room_service = RoomService(session)
        membership = await room_service._get_user_membership(user_id)
        if not membership or membership.room_id != room_id:
            return None, None

    return user_id, room_id


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    user_id, room_id = await authenticate_ws(websocket)
    if not user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    # Register connection and auto-join room
    await manager.connect(websocket, user_id)
    await manager.join_room(user_id, room_id)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send_to_user(user_id, {
                    "type": "error",
                    "detail": "Invalid JSON",
                })
                continue

            msg_type = data.get("type")
            await _handle_message(user_id, room_id, msg_type, data)

    except WebSocketDisconnect:
        await manager.disconnect(user_id, reason="client_disconnect")


async def _handle_message(user_id: str, room_id: str, msg_type: str | None, data: dict) -> None:
    """Route incoming messages to the appropriate handler."""

    if msg_type == "pong":
        await manager.handle_pong(user_id)

    elif msg_type == "location":
        await manager.broadcast_to_room(
            room_id,
            {
                "type": "location",
                "user_id": user_id,
                "lat": data.get("lat"),
                "lng": data.get("lng"),
                "speed": data.get("speed"),
                "heading": data.get("heading"),
                "ts": data.get("ts"),
            },
            exclude=user_id,
        )

    elif msg_type == "message":
        await manager.broadcast_to_room(
            room_id,
            {
                "type": "message",
                "user_id": user_id,
                "text": data.get("text", ""),
            },
            exclude=user_id,
        )

    else:
        await manager.send_to_user(user_id, {
            "type": "error",
            "detail": f"Unknown message type: {msg_type}",
        })
