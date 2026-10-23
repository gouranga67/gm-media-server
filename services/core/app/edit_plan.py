import hashlib
import json
from collections import defaultdict
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


EDIT_PLAN_SCHEMA_VERSION = "1.0"
MAX_PREVIEW_SECONDS = 60.0
MAX_CLIPS = 24


class EditClip(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: UUID
    source_in: float = Field(ge=0)
    source_out: float = Field(gt=0)
    crop: Literal["center_fill"]
    transition: Literal["cut"]

    @model_validator(mode="after")
    def source_range_is_forward(self) -> "EditClip":
        if self.source_out - self.source_in < 0.25:
            raise ValueError("each clip must be at least 0.25 seconds long")
        return self


class TalkingHeadEditPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    recipe: Literal["talking_head"]
    clips: list[EditClip] = Field(min_length=1, max_length=MAX_CLIPS)
    caption_style: Literal["clean_blue_v1"]
    audio_preset: Literal["spoken_voice_v1"]
    end_card: Literal["none"]
    editorial_summary: str = Field(min_length=1, max_length=600)
    post_copy: str = Field(default="", max_length=2200)


# This schema is intentionally small and contains only Structured Outputs
# features supported by the Responses API. Every property is required and all
# objects reject unknown keys.
EDIT_PLAN_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string", "enum": [EDIT_PLAN_SCHEMA_VERSION]},
        "recipe": {"type": "string", "enum": ["talking_head"]},
        "clips": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_CLIPS,
            "items": {
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string", "format": "uuid"},
                    "source_in": {"type": "number", "minimum": 0},
                    "source_out": {"type": "number", "exclusiveMinimum": 0},
                    "crop": {"type": "string", "enum": ["center_fill"]},
                    "transition": {"type": "string", "enum": ["cut"]},
                },
                "required": ["asset_id", "source_in", "source_out", "crop", "transition"],
                "additionalProperties": False,
            },
        },
        "caption_style": {"type": "string", "enum": ["clean_blue_v1"]},
        "audio_preset": {"type": "string", "enum": ["spoken_voice_v1"]},
        "end_card": {"type": "string", "enum": ["none"]},
        "editorial_summary": {"type": "string", "minLength": 1, "maxLength": 600},
        "post_copy": {"type": "string", "maxLength": 2200},
    },
    "required": [
        "schema_version",
        "recipe",
        "clips",
        "caption_style",
        "audio_preset",
        "end_card",
        "editorial_summary",
        "post_copy",
    ],
    "additionalProperties": False,
}


def document_sha256(document: dict[str, Any]) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_edit_plan(
    document: dict[str, Any],
    assets: list[dict[str, Any]],
    *,
    allow_post_copy: bool = False,
) -> TalkingHeadEditPlan:
    plan = TalkingHeadEditPlan.model_validate(document)
    if plan.post_copy and not allow_post_copy:
        raise ValueError("AI-written post copy was not enabled for this project")
    inventory = {str(asset["asset_id"]): asset for asset in assets}
    ranges: dict[str, list[tuple[float, float]]] = defaultdict(list)
    total_duration = 0.0

    for clip in plan.clips:
        asset_id = str(clip.asset_id)
        asset = inventory.get(asset_id)
        if asset is None:
            raise ValueError(f"asset {asset_id} does not belong to this job")
        if not asset.get("has_video"):
            raise ValueError(f"asset {asset_id} is not a video source")
        if not asset.get("has_audio"):
            raise ValueError(f"asset {asset_id} has no audio for the talking-head recipe")

        duration = float(asset.get("duration_seconds") or 0)
        if clip.source_out > duration + 0.01:
            raise ValueError(
                f"asset {asset_id} ends at {duration:.3f}s, before requested "
                f"source_out {clip.source_out:.3f}s"
            )
        ranges[asset_id].append((clip.source_in, clip.source_out))
        total_duration += clip.source_out - clip.source_in

    if total_duration > MAX_PREVIEW_SECONDS + 0.01:
        raise ValueError(f"preview duration {total_duration:.3f}s exceeds 60 seconds")

    for asset_id, asset_ranges in ranges.items():
        ordered = sorted(asset_ranges)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current[0] < previous[1] - 0.01:
                raise ValueError(f"asset {asset_id} contains overlapping source ranges")

    return plan


def deterministic_plan(assets: list[dict[str, Any]]) -> TalkingHeadEditPlan:
    """Create the fixed local-only recipe without invoking a model."""

    candidates = [asset for asset in assets if asset.get("has_video") and asset.get("has_audio")]
    if not candidates:
        raise ValueError("the talking-head recipe needs a video asset with audio")
    asset = candidates[0]
    duration = min(float(asset.get("duration_seconds") or 0), 45.0)
    if duration < 0.25:
        raise ValueError("the source video is too short to edit")
    plan = TalkingHeadEditPlan(
        schema_version="1.0",
        recipe="talking_head",
        clips=[
            EditClip(
                asset_id=UUID(str(asset["asset_id"])),
                source_in=0.0,
                source_out=round(duration, 3),
                crop="center_fill",
                transition="cut",
            )
        ],
        caption_style="clean_blue_v1",
        audio_preset="spoken_voice_v1",
        end_card="none",
        editorial_summary="Local-only fixed recipe using the first eligible source clip.",
        post_copy="",
    )
    return validate_edit_plan(plan.model_dump(mode="json"), assets)
