from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StringEnum(str, Enum):
    """String-valued enum compatible with both API and CUDA worker Python."""

    def __str__(self) -> str:
        return str(self.value)


class PrivacyMode(StringEnum):
    HYBRID = "hybrid"
    TEXT_ONLY = "text_only"
    LOCAL_ONLY = "local_only"


class Recipe(StringEnum):
    TALKING_HEAD = "talking_head"
    MONTAGE = "montage"


class EditStyle(StringEnum):
    CLEAN = "clean"
    ENERGETIC = "energetic"
    CALM = "calm"


class MusicMode(StringEnum):
    NONE = "none"
    SUBTLE = "subtle"
    PRESENT = "present"


class TargetPlatform(StringEnum):
    ALL_SOCIAL = "all_social"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    LINKEDIN = "linkedin"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"


class ReasoningEffort(StringEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OutputAspect(StringEnum):
    VERTICAL = "vertical"
    LANDSCAPE = "landscape"
    SQUARE = "square"


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
    target_duration_seconds: Literal[15, 20, 30, 45, 60] = 45
    edit_style: EditStyle = EditStyle.ENERGETIC
    music_mode: MusicMode = MusicMode.NONE
    target_platform: TargetPlatform = TargetPlatform.ALL_SOCIAL
    must_include: str = Field(default="", max_length=2000)
    editor_model: str | None = Field(default=None, min_length=1, max_length=160)
    reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM
    output_aspect: OutputAspect = OutputAspect.VERTICAL
    creative_profile_id: UUID | None = None

    @field_validator("must_include")
    @classmethod
    def normalize_must_include(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("editor_model")
    @classmethod
    def normalize_editor_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
        if not normalized or any(character not in allowed for character in normalized):
            raise ValueError("editor model contains unsupported characters")
        return normalized


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
    editor_model: str | None = None
    reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM
    output_aspect: OutputAspect = OutputAspect.VERTICAL
    creative_profile_id: UUID | None = None
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


class LibraryAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    project_name: str
    source_name: str
    mime_type: str
    byte_size: int
    sha256: str
    duration_seconds: float | None = None
    thumbnail_available: bool = False
    created_at: datetime


class CatalogSearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    segment_id: int
    asset_id: UUID
    project_id: UUID
    project_name: str
    source_name: str
    mime_type: str
    byte_size: int
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    duration_seconds: float | None = None
    thumbnail_available: bool = False
    segment_kind: Literal["asset", "transcript", "scene", "image", "visual"]
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    text: str
    facts: dict[str, Any] = Field(default_factory=dict)
    source_model: str
    rank: float = Field(ge=0)
    evidence_kinds: list[Literal["metadata", "spoken_words", "visual"]] = Field(default_factory=list)
    visual_frame_id: int | None = None
    visual_frame_seconds: float | None = Field(default=None, ge=0)
    created_at: datetime


class CatalogSearchResponse(BaseModel):
    query: str
    total: int = Field(ge=0)
    results: list[CatalogSearchResult] = Field(default_factory=list)


class CatalogStatusResponse(BaseModel):
    assets_total: int = Field(ge=0)
    assets_ready: int = Field(ge=0)
    assets_pending: int = Field(ge=0)
    assets_failed: int = Field(ge=0)
    segments_total: int = Field(ge=0)
    transcript_segments: int = Field(ge=0)
    scene_segments: int = Field(ge=0)
    catalog_version: str


class VisualIndexStatusResponse(BaseModel):
    assets_total: int = Field(ge=0)
    assets_ready: int = Field(ge=0)
    assets_aliased: int = Field(ge=0)
    assets_pending: int = Field(ge=0)
    assets_failed: int = Field(ge=0)
    frames_total: int = Field(ge=0)
    model_id: str
    model_revision: str
    index_version: str
    local_only: bool = True


class VisualReindexResponse(BaseModel):
    queued_assets: int = Field(ge=0)


class ManagedLibraryAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    project_name: str
    source_name: str
    display_name: str
    notes: str = ""
    favorite: bool = False
    tags: list[str] = Field(default_factory=list)
    library_status: Literal["active", "archived"]
    mime_type: str
    byte_size: int
    sha256: str
    duration_seconds: float | None = None
    thumbnail_available: bool = False
    job_references: int = Field(ge=0)
    collection_count: int = Field(ge=0)
    visual_status: str | None = None
    created_at: datetime
    updated_at: datetime


class LibraryAssetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    notes: str = Field(default="", max_length=4000)
    favorite: bool = False
    tags: list[str] = Field(default_factory=list, max_length=25)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("display name cannot be blank")
        return normalized

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in value:
            tag = " ".join(raw.split()).lower()
            if not tag or len(tag) > 40:
                raise ValueError("tags must contain between 1 and 40 characters")
            if tag not in seen:
                normalized.append(tag)
                seen.add(tag)
        return normalized


class LibraryEvidenceSegment(BaseModel):
    id: int
    segment_kind: Literal["transcript", "scene", "image"]
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    text: str
    source_model: str


class LibraryVisualFrame(BaseModel):
    id: int
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    frame_seconds: float = Field(ge=0)


class LibraryCollectionResponse(BaseModel):
    id: UUID
    name: str
    description: str
    asset_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class LibraryCollectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("collection name cannot be blank")
        return normalized


class LibraryAssetDetailResponse(BaseModel):
    asset: ManagedLibraryAssetResponse
    evidence: list[LibraryEvidenceSegment] = Field(default_factory=list)
    visual_frames: list[LibraryVisualFrame] = Field(default_factory=list)
    collections: list[LibraryCollectionResponse] = Field(default_factory=list)


class LibraryAssetStateResponse(BaseModel):
    asset_id: UUID
    library_status: Literal["active", "archived"]


class JobAssetAttach(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_ids: list[UUID] = Field(min_length=1, max_length=100)

    @field_validator("asset_ids")
    @classmethod
    def asset_ids_are_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("asset IDs cannot repeat")
        return value


class JobAssetAttachResponse(BaseModel):
    job_id: UUID
    asset_ids: list[UUID]
    attached_count: int


class DuplicateAssetCopyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    project_name: str
    source_name: str
    mime_type: str
    byte_size: int
    job_references: int = 0
    thumbnail_available: bool = False
    storage_optimized: bool = False
    created_at: datetime


class DuplicateGroupResponse(BaseModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_kind: Literal["video", "image", "audio"]
    mime_type: str
    byte_size: int
    copy_count: int = Field(ge=2)
    reclaimable_bytes: int = Field(ge=0)
    canonical_asset_id: UUID
    canonical_reason: str
    reviewed: bool = False
    reviewed_at: datetime | None = None
    cleanup_ready: bool = False
    optimized_copies: int = Field(default=0, ge=0)
    copies: list[DuplicateAssetCopyResponse] = Field(min_length=2)


class DuplicateAuditSummary(BaseModel):
    originals_scanned: int = Field(ge=0)
    duplicate_groups: int = Field(ge=0)
    unreviewed_groups: int = Field(ge=0)
    redundant_copies: int = Field(ge=0)
    optimized_copies: int = Field(default=0, ge=0)
    reclaimable_bytes: int = Field(ge=0)


class DuplicateAuditResponse(BaseModel):
    summary: DuplicateAuditSummary
    groups: list[DuplicateGroupResponse] = Field(default_factory=list)


class DuplicateReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_asset_id: UUID


class DuplicateReviewResponse(BaseModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_asset_id: UUID
    asset_count: int = Field(ge=2)
    reviewed_at: datetime


class DuplicateCleanupCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_asset_id: UUID
    confirmation: Literal["share_verified_storage"]


class DuplicateCleanupResponse(BaseModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_asset_id: UUID
    optimized_asset_ids: list[UUID]
    optimized_copies: int = Field(ge=0)
    bytes_reclaimed: int = Field(ge=0)
    already_optimized: int = Field(ge=0)


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
    beat_grid_seconds: list[float] = Field(default_factory=list)
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
    reasoning_effort: ReasoningEffort | None = None
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


class CreativeProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=400)
    recipe: Recipe
    target_duration_seconds: Literal[15, 20, 30, 45, 60]
    edit_style: EditStyle
    music_mode: MusicMode
    target_platform: TargetPlatform
    output_aspect: OutputAspect
    reasoning_effort: ReasoningEffort
    source_job_id: UUID | None = None

    @field_validator("name", "description")
    @classmethod
    def normalize_profile_text(cls, value: str) -> str:
        return " ".join(value.split())


class CreativeProfileResponse(CreativeProfileCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class CreativeProfileFromJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=400)

    @field_validator("name", "description")
    @classmethod
    def normalize_profile_text(cls, value: str) -> str:
        return " ".join(value.split())


class DeliveryVariantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_aspect: OutputAspect
    target_duration_seconds: Literal[15, 20, 30, 45, 60]


class DeliveryVariantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    edit_run_id: UUID
    version: int
    output_aspect: OutputAspect
    target_duration_seconds: int
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


class EditorModelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    display_name: str
    provider: str
    available: bool
    refreshed_at: datetime


class AiUsageEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    edit_run_id: UUID
    provider: str
    model: str
    reasoning_effort: ReasoningEffort | None = None
    request_kind: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    latency_ms: int
    created_at: datetime


class JobUsageSummary(BaseModel):
    requests: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0
    events: list[AiUsageEventResponse] = Field(default_factory=list)


class UsageModelSummary(BaseModel):
    model: str
    requests: int
    total_tokens: int


class UsageJobSummary(BaseModel):
    id: UUID
    project_name: str
    recipe: Recipe
    status: str
    created_at: datetime
    model: str | None = None
    requests: int = 0
    total_tokens: int = 0
    history_kind: Literal["editing", "verification"] = "editing"


class UsageDashboardResponse(BaseModel):
    days: int
    requests: int
    jobs: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    by_model: list[UsageModelSummary]
    job_history: list[UsageJobSummary]


class JobReviewResponse(BaseModel):
    job: JobResponse
    versions: list[EditRunResponse]
    latest_run: EditRunResponse | None = None
    final_export: FinalExportResponse | None = None
    delivery_variants: list[DeliveryVariantResponse] = Field(default_factory=list)
    events: list[JobEventResponse]
    usage: JobUsageSummary = Field(default_factory=JobUsageSummary)
