from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserSignup(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def trim_username(cls, v: str) -> str:
        return v.strip()


class UserLogin(BaseModel):
    identifier: str = Field(min_length=3, description="Email or username")
    password: str

    @field_validator("identifier")
    @classmethod
    def trim_identifier(cls, v: str) -> str:
        return v.strip()


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    refresh_token: str


class WsTokenResponse(BaseModel):
    ws_token: str
    expires_in_seconds: int


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    is_active: bool
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}
