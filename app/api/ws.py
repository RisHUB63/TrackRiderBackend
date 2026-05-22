"""
WebSocket API Endpoint

Protocol:
- Client connects with ?token=<ws_token>
- Server authenticates and accepts
- Client sends JSON messages with a "type" field
- Server responds/broadcasts based on message type

Message Types (client -> server):
  {"type": "pong"}                     - Heartbeat response
  {"type": "join_room", "room_id": "..."} - Join a socket room
  {"type": "leave_room"}               - Leave current room
  {"type": "location", "lat": ..., "lng": ..., "speed": ...} - Share location
  {"type": "message", "text": "..."}   - Send text to room

Message Types (server -> client):
  {"type": "ping", "ts": ...}          - Heartbeat ping
  {"type": "room_joined", "room_id": ..., "members": [...]}
  {"type": "member_joined", "user_id": ...}
  {"type": "member_left", "user_id": ...}
  {"type": "location", "user_id": ..., "lat": ..., "lng": ..., "speed": ...}
  {"type": "message", "user_id": ..., "text": ...}
  {"type": "error", "detail": "..."}
"""

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.database import async_session_factory
from app.core.security import decode_token
from app.services.user_repository import UserRepository
from app.services.ws_manager import manager

router = APIRouter(tags=["websocket"])


async def authenticate_ws(websocket: WebSocket) -> str | None:
    """Validate WS token from query params and return user_id or None."""
    token = websocket.query_params.get("token")
    if not token:
        return None

    payload = decode_token(token)
    if not payload or payload.get("type") != "ws":
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if not user or not user.is_active:
            return None

    return user_id


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    user_id = await authenticate_ws(websocket)
    if not user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    conn = await manager.connect(websocket, user_id)

    # Send welcome message with connection info
    await manager.send_to_user(user_id, {
        "type": "connected",
        "user_id": user_id,
        "message": "Connection established",
    })

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
            await _handle_message(user_id, msg_type, data)

    except WebSocketDisconnect:
        await manager.disconnect(user_id, reason="client_disconnect")


async def _handle_message(user_id: str, msg_type: str | None, data: dict) -> None:
    """Route incoming messages to the appropriate handler."""

    if msg_type == "pong":
        await manager.handle_pong(user_id)

    elif msg_type == "join_room":
        room_id = data.get("room_id")
        if not room_id:
            await manager.send_to_user(user_id, {
                "type": "error",
                "detail": "room_id is required",
            })
            return
        await manager.join_room(user_id, room_id)

    elif msg_type == "leave_room":
        await manager.leave_room(user_id)
        await manager.send_to_user(user_id, {"type": "room_left"})

    elif msg_type == "location":
        conn = manager.get_connection(user_id)
        if not conn or not conn.room_id:
            await manager.send_to_user(user_id, {
                "type": "error",
                "detail": "Join a room first",
            })
            return
        await manager.broadcast_to_room(
            conn.room_id,
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
        conn = manager.get_connection(user_id)
        if not conn or not conn.room_id:
            await manager.send_to_user(user_id, {
                "type": "error",
                "detail": "Join a room first",
            })
            return
        await manager.broadcast_to_room(
            conn.room_id,
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
