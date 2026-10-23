from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PrivacyMode(StrEnum):
    HYBRID = "hybrid"
    TEXT_ONLY = "text_only"
    LOCAL_ONLY = "local_only"


class Recipe(StrEnum):
    TALKING_HEAD = "talking_head"


class EditStyle(StrEnum):
    CLEAN = "clean"
    ENERGETIC = "energetic"
    CALM = "calm"


class MusicMode(StrEnum):
    NONE = "none"
    SUBTLE = "subtle"
    PRESENT = "present"


class TargetPlatform(StrEnum):
    ALL_SOCIAL = "all_social"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    LINKEDIN = "linkedin"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"


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
    target_duration_seconds: Literal[20, 30, 45, 60] = 45
    edit_style: EditStyle = EditStyle.ENERGETIC
    music_mode: MusicMode = MusicMode.NONE
    target_platform: TargetPlatform = TargetPlatform.ALL_SOCIAL
    must_include: str = Field(default="", max_length=2000)

    @field_validator("must_include")
    @classmethod
    def normalize_must_include(cls, value: str) -> str:
        return " ".join(value.split())


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    recipe: Recipe
    status: str
    revision: int
    target_duration_seconds: int | None = None
    edit_style: EditStyle | None = None
    music_mode: MusicMode | None = None
    target_platform: TargetPlatform | None = None
    must_include: str = ""
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


class MusicTrackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    artist: str
    duration_seconds: float
    mood: str
    energy: str
    bpm: float | None = None
    license_name: str
    license_source_url: str
    allowed_platforms: list[str] = Field(default_factory=list)
    attribution: str
    created_at: datetime


class EditRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    version: int
    status: str
    attempts: int
    provider: str | None = None
    model: str | None = None
    based_on_run_id: UUID | None = None
    revision_note: str | None = None
    caption_corrections: list[dict[str, str]] = Field(default_factory=list)
    approved_at: datetime | None = None
    preview_available: bool = False
    manifest: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CaptionCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_text: str = Field(min_length=1, max_length=300)
    replacement_text: str = Field(min_length=1, max_length=300)

    @field_validator("original_text", "replacement_text")
    @classmethod
    def normalize_caption_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("caption text cannot be blank")
        return normalized

    @model_validator(mode="after")
    def text_changes(self) -> "CaptionCorrection":
        if self.original_text == self.replacement_text:
            raise ValueError("caption correction must change the text")
        return self


class RevisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(default="", max_length=1200)
    caption_corrections: list[CaptionCorrection] = Field(default_factory=list, max_length=50)

    @field_validator("note")
    @classmethod
    def normalize_revision_note(cls, value: str) -> str:
        return " ".join(value.split())

    @model_validator(mode="after")
    def has_requested_change(self) -> "RevisionCreate":
        if not self.note and not self.caption_corrections:
            raise ValueError("provide a revision note or at least one caption correction")
        originals = [item.original_text for item in self.caption_corrections]
        if len(originals) != len(set(originals)):
            raise ValueError("caption corrections cannot repeat the same original text")
        return self


class ApprovalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(gt=0)
    note: str = Field(default="", max_length=1000)


class FinalExportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    edit_run_id: UUID
    version: int
    status: str
    attempts: int
    files_available: bool = False
    post_copy_available: bool = False
    manifest: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class JobEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class JobReviewResponse(BaseModel):
    job: JobResponse
    versions: list[EditRunResponse]
    latest_run: EditRunResponse | None = None
    final_export: FinalExportResponse | None = None
    events: list[JobEventResponse]
