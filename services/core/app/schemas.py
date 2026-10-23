from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PrivacyMode(StrEnum):
    HYBRID = "hybrid"
    TEXT_ONLY = "text_only"
    LOCAL_ONLY = "local_only"


class Recipe(StrEnum):
    TALKING_HEAD = "talking_head"


class ProjectCreate(BaseModel):
    id: UUID | None = None
    name: str = Field(min_length=1, max_length=160)
    brief: str = Field(default="", max_length=4000)
    privacy_mode: PrivacyMode = PrivacyMode.HYBRID
    ai_copy_allowed: bool = False


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    brief: str
    privacy_mode: PrivacyMode
    ai_copy_allowed: bool
    created_at: datetime
    updated_at: datetime


class JobCreate(BaseModel):
    id: UUID | None = None
    recipe: Recipe = Recipe.TALKING_HEAD


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    recipe: Recipe
    status: str
    revision: int
    created_at: datetime
    updated_at: datetime


class AssetCreate(BaseModel):
    id: UUID | None = None
    job_id: UUID | None = None
    source_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=160)
    byte_size: int = Field(gt=0)

    @field_validator("mime_type")
    @classmethod
    def validate_media_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized.startswith(("video/", "image/", "audio/")):
            raise ValueError("only video, image, and audio uploads are accepted")
        return normalized


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    source_name: str
    storage_key: str
    mime_type: str | None
    byte_size: int | None
    status: str
    tus_upload_id: str | None = None
    sha256: str | None = None
    created_at: datetime
    updated_at: datetime


class AssetAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: UUID
    project_id: UUID
    status: str
    attempts: int
    manifest_path: str | None = None
    manifest: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class EditRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    version: int
    status: str
    attempts: int
    provider: str | None = None
    model: str | None = None
    preview_available: bool = False
    manifest: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
