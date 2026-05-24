from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class RoomType(str, Enum):
    ride = "ride"
    track = "track"


class CreateRoomRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: RoomType
    max_members: int | None = Field(default=None, ge=2)


class JoinRoomRequest(BaseModel):
    code: str


class RoomResponse(BaseModel):
    id: str
    name: str
    code: str
    type: RoomType
    max_members: int | None
    is_active: bool
    created_by: str
    created_at: datetime
    member_count: int = 0

    model_config = {"from_attributes": True}


class RoomMemberResponse(BaseModel):
    id: str
    user_id: str
    email: str
    joined_at: datetime
    is_admin: bool = False
