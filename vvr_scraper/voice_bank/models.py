"""Pydantic request/response models for the voice bank API."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# --- Request Models ---


class VoiceUploadRequest(BaseModel):
    """Validated fields from multipart upload (validated in router, not here)."""

    name: str = Field(min_length=3, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    ref_text: str = Field(min_length=10, max_length=5000)
    gender: Literal["male", "female", "other"]
    age_group: Literal["child", "teen", "young_adult", "adult", "elder"]
    language: str = Field(default="vi")
    mood: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        for tag in v:
            if len(tag) > 15:
                raise ValueError(f"Tag '{tag}' exceeds 15 characters")
            if not tag.replace("-", "").replace("_", "").isalnum():
                raise ValueError(f"Tag '{tag}' must be a single word (letters, numbers, hyphens, underscores)")
        return [tag.lower().strip() for tag in v]


class VoiceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    mood: str | None = None
    tags: list[str] | None = Field(default=None, max_length=5)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        for tag in v:
            if len(tag) > 15:
                raise ValueError(f"Tag '{tag}' exceeds 15 characters")
            if not tag.replace("-", "").replace("_", "").isalnum():
                raise ValueError(f"Tag '{tag}' must be a single word")
        return [tag.lower().strip() for tag in v]


class VoiceVoteRequest(BaseModel):
    vote: Literal[1, -1]


class VoicePreviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


# --- Response Models ---


class VoiceSampleResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: str | None
    ref_audio_path: str
    ref_text: str
    duration_ms: int
    sample_rate: int
    gender: str
    age_group: str
    language: str
    mood: str | None
    visibility: str
    usage_count: int
    tags: list[str]
    vote_score: int
    created_at: str
    updated_at: str


class VoiceListResponse(BaseModel):
    items: list[VoiceSampleResponse]
    total: int
