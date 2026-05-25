import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.database import async_session_factory
from app.core.security import decode_token
from app.services.room_service import RoomService
from app.services.user_repository import UserRepository
from app.services.ws_manager import manager

router = APIRouter(tags=["websocket"])


async def authenticate_ws(
    websocket: WebSocket,
) -> tuple[str | None, str | None, str | None]:
    """Validate WS token and room code. Returns (user_id, username, room_id) or (None, None, None)."""
    token = websocket.query_params.get("token")
    code = websocket.query_params.get("code") or websocket.query_params.get("room_id")

    if not token or not code:
        return None, None, None

    code = code.strip().upper()

    payload = decode_token(token)
    if not payload or payload.get("type") != "ws":
        return None, None, None

    user_id = payload.get("sub")
    if not user_id:
        return None, None, None

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if not user or not user.is_active:
            return None, None, None

        # Resolve code to room and verify membership
        room_service = RoomService(session)
        room = await room_service.get_room_by_code(code)
        if not room or not room.is_active:
            return None, None, None

        membership = await room_service._get_active_membership(user_id)
        if not membership or membership.room_id != room.id:
            return None, None, None

    return user_id, user.username, room.id


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    user_id, username, room_id = await authenticate_ws(websocket)
    if not user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    # Register connection and auto-join room
    await manager.connect(websocket, user_id, username)
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
            await _handle_message(user_id, username, room_id, msg_type, data)

    except WebSocketDisconnect:
        await manager.disconnect(user_id, reason="client_disconnect")


async def _handle_message(
    user_id: str, username: str, room_id, msg_type: str | None, data: dict
) -> None:
    """Route incoming messages to the appropriate handler."""

    if msg_type == "pong":
        await manager.handle_pong(user_id)

    elif msg_type == "location":
        await manager.broadcast_to_room(
            room_id,
            {
                "type": "location",
                "username": username,
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
                "username": username,
                "text": data.get("text", ""),
            },
            exclude=user_id,
        )

    else:
        await manager.send_to_user(user_id, {
            "type": "error",
            "detail": f"Unknown message type: {msg_type}",
        })
