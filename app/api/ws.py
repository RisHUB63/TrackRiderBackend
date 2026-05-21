from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.database import async_session_factory
from app.core.security import decode_token
from app.services.user_repository import UserRepository

router = APIRouter(tags=["websocket"])


async def authenticate_ws(websocket: WebSocket) -> str | None:
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
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"user={user_id}: {data}")
    except WebSocketDisconnect:
        pass
