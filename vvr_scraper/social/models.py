from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ReactionType = Literal[
    "heart", "cry", "wow", "angry", "fire", "skull", "think", "clap", "nerd", "laugh", "eyes", "pray", "sparkles"
]
UserRole = Literal["admin", "member"]


class SocialUser(BaseModel):
    id: str
    username: str
    display_name: str
    role: UserRole
    created_at: datetime


class RegisterRequest(BaseModel):
    invite_code: str
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class InviteCreateRequest(BaseModel):
    max_uses: int = Field(default=1, ge=1, le=100)


class ReactionCreateRequest(BaseModel):
    anchor: str = Field(min_length=1, max_length=1000)
    reaction_type: ReactionType


class CommentCreateRequest(BaseModel):
    anchor: str | None = Field(default=None, max_length=1000)
    content: str = Field(min_length=1, max_length=2000)
    parent_id: str | None = None

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value


class CommentUpdateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
