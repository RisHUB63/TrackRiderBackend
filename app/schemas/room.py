from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class RoomType(str, Enum):
    ride = "ride"
    track = "track"


class MemberStatus(str, Enum):
    admin = "admin"
    member = "member"


class CreateRoomRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: RoomType
    max_members: int | None = Field(default=None, ge=2)


class JoinRoomRequest(BaseModel):
    code: str = Field(min_length=1, max_length=16)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, v: str) -> str:
        return v.strip().upper()


class RoomResponse(BaseModel):
    name: str
    code: str
    type: RoomType
    max_members: int | None
    is_active: bool
    created_by: str  # username of the creator
    created_at: datetime
    member_count: int = 0

    model_config = {"from_attributes": True}


class RoomMemberResponse(BaseModel):
    username: str
    joined_at: datetime
    status: MemberStatus
