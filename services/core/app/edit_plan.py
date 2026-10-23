import hashlib
import json
from collections import defaultdict
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


EDIT_PLAN_SCHEMA_VERSION = "1.1"
MAX_PREVIEW_SECONDS = 60.0
MAX_CLIPS = 24
TARGET_DURATION_RANGES = {
    20: (15.0, 25.0),
    30: (24.0, 36.0),
    45: (36.0, 52.0),
    60: (48.0, 60.0),
}


class EditClip(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: UUID
    source_in: float = Field(ge=0)
    source_out: float = Field(gt=0)
    crop: Literal["center_fill"]
    transition: Literal["cut", "dip_to_black"] = "cut"
    visual_preset: Literal[
        "standard",
        "punch_in",
        "strong_punch_in",
        "slow_push_in",
        "slow_pull_out",
    ] = "standard"

    @model_validator(mode="after")
    def source_range_is_forward(self) -> "EditClip":
        if self.source_out - self.source_in < 0.25:
            raise ValueError("each clip must be at least 0.25 seconds long")
        return self


class TalkingHeadEditPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0", "1.1"]
    recipe: Literal["talking_head"]
    clips: list[EditClip] = Field(min_length=1, max_length=MAX_CLIPS)
    caption_style: Literal["clean_blue_v1"]
    audio_preset: Literal["spoken_voice_v1"]
    end_card: Literal["none"]
    editorial_summary: str = Field(min_length=1, max_length=600)
    post_copy: str = Field(default="", max_length=2200)
    music_track_id: UUID | None = None
    music_mix: Literal["none", "subtle", "present"] = "none"


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
                    "transition": {"type": "string", "enum": ["cut", "dip_to_black"]},
                    "visual_preset": {
                        "type": "string",
                        "enum": [
                            "standard",
                            "punch_in",
                            "strong_punch_in",
                            "slow_push_in",
                            "slow_pull_out",
                        ],
                    },
                },
                "required": [
                    "asset_id",
                    "source_in",
                    "source_out",
                    "crop",
                    "transition",
                    "visual_preset",
                ],
                "additionalProperties": False,
            },
        },
        "caption_style": {"type": "string", "enum": ["clean_blue_v1"]},
        "audio_preset": {"type": "string", "enum": ["spoken_voice_v1"]},
        "end_card": {"type": "string", "enum": ["none"]},
        "editorial_summary": {"type": "string", "minLength": 1, "maxLength": 600},
        "post_copy": {"type": "string", "maxLength": 2200},
        "music_track_id": {"type": ["string", "null"], "format": "uuid"},
        "music_mix": {"type": "string", "enum": ["none", "subtle", "present"]},
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
        "music_track_id",
        "music_mix",
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
    creative_direction: dict[str, Any] | None = None,
    music_tracks: list[dict[str, Any]] | None = None,
) -> TalkingHeadEditPlan:
    plan = TalkingHeadEditPlan.model_validate(document)
    if plan.post_copy and not allow_post_copy:
        raise ValueError("AI-written post copy was not enabled for this project")
    inventory = {str(asset["asset_id"]): asset for asset in assets}
    ranges: dict[str, list[tuple[float, float]]] = defaultdict(list)
    total_duration = 0.0

    for index, clip in enumerate(plan.clips):
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
        clip_duration = clip.source_out - clip.source_in
        if index == 0 and clip.transition != "cut":
            raise ValueError("the first clip must begin with a cut")
        if clip.visual_preset in {"slow_push_in", "slow_pull_out"} and clip_duration < 2.0:
            raise ValueError("animated zoom presets require clips of at least 2 seconds")

    if total_duration > MAX_PREVIEW_SECONDS + 0.01:
        raise ValueError(f"preview duration {total_duration:.3f}s exceeds 60 seconds")

    direction = creative_direction or {}
    target = direction.get("target_duration_seconds")
    if target in TARGET_DURATION_RANGES:
        minimum, maximum = TARGET_DURATION_RANGES[target]
        available = sum(
            float(asset.get("duration_seconds") or 0)
            for asset in assets
            if asset.get("has_video") and asset.get("has_audio")
        )
        minimum = min(minimum, max(0.25, available - 0.5))
        if total_duration < minimum - 0.01:
            raise ValueError(
                f"edit duration {total_duration:.3f}s is below the {minimum:.3f}s floor "
                f"for a {target}s target"
            )
        if total_duration > maximum + 0.01:
            raise ValueError(
                f"edit duration {total_duration:.3f}s exceeds the {maximum:.3f}s ceiling "
                f"for a {target}s target"
            )

    style = direction.get("edit_style")
    strong_punches = sum(clip.visual_preset == "strong_punch_in" for clip in plan.clips)
    visual_emphasis_count = sum(clip.visual_preset != "standard" for clip in plan.clips)
    transition_count = sum(clip.transition != "cut" for clip in plan.clips)
    if style == "clean" and strong_punches > 1:
        raise ValueError("the clean style permits at most one strong punch-in")
    if style == "calm" and strong_punches:
        raise ValueError("the calm style does not permit strong punch-ins")
    if strong_punches > 5:
        raise ValueError("an edit may contain at most five strong punch-ins")
    if style == "energetic" and total_duration >= 8 and visual_emphasis_count == 0:
        raise ValueError("the energetic style requires at least one bounded visual emphasis")
    if style == "energetic" and total_duration >= 20 and transition_count == 0:
        raise ValueError("an energetic edit of 20 seconds or longer requires a transition beat")

    tracks = {str(track["track_id"]): track for track in music_tracks or []}
    requested_music = direction.get("music_mode") or "none"
    if plan.music_track_id is None:
        if plan.music_mix != "none":
            raise ValueError("a music mix requires an approved music track")
        if requested_music != "none" and tracks:
            raise ValueError("this job requested music but the edit plan did not select a track")
    else:
        track_id = str(plan.music_track_id)
        if requested_music == "none":
            raise ValueError("music was not enabled for this job")
        if track_id not in tracks:
            raise ValueError(f"music track {track_id} is not in the approved library")
        if plan.music_mix != requested_music:
            raise ValueError("the music mix does not match the job's requested music level")

    for asset_id, asset_ranges in ranges.items():
        ordered = sorted(asset_ranges)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current[0] < previous[1] - 0.01:
                raise ValueError(f"asset {asset_id} contains overlapping source ranges")

    return plan


def deterministic_plan(
    assets: list[dict[str, Any]],
    target_duration_seconds: int | None = None,
    edit_style: str = "clean",
    music_mode: str = "none",
    music_tracks: list[dict[str, Any]] | None = None,
) -> TalkingHeadEditPlan:
    """Create the fixed local-only recipe without invoking a model."""

    candidates = [asset for asset in assets if asset.get("has_video") and asset.get("has_audio")]
    if not candidates:
        raise ValueError("the talking-head recipe needs a video asset with audio")
    asset = candidates[0]
    requested = float(target_duration_seconds or 45)
    duration = min(float(asset.get("duration_seconds") or 0), requested, MAX_PREVIEW_SECONDS)
    if duration < 0.25:
        raise ValueError("the source video is too short to edit")
    selected_track = (music_tracks or [None])[0] if music_mode != "none" else None
    if edit_style == "energetic" and duration >= 4:
        split = round(duration / 2, 3)
        clips = [
            EditClip(
                asset_id=UUID(str(asset["asset_id"])),
                source_in=0.0,
                source_out=split,
                crop="center_fill",
                transition="cut",
                visual_preset="standard",
            ),
            EditClip(
                asset_id=UUID(str(asset["asset_id"])),
                source_in=split,
                source_out=round(duration, 3),
                crop="center_fill",
                transition="dip_to_black",
                visual_preset="punch_in",
            ),
        ]
    else:
        clips = [
            EditClip(
                asset_id=UUID(str(asset["asset_id"])),
                source_in=0.0,
                source_out=round(duration, 3),
                crop="center_fill",
                transition="cut",
                visual_preset="slow_push_in" if edit_style == "calm" and duration >= 2 else "standard",
            )
        ]
    plan = TalkingHeadEditPlan(
        schema_version=EDIT_PLAN_SCHEMA_VERSION,
        recipe="talking_head",
        clips=clips,
        caption_style="clean_blue_v1",
        audio_preset="spoken_voice_v1",
        end_card="none",
        editorial_summary="Local-only fixed recipe using the first eligible source clip.",
        post_copy="",
        music_track_id=(
            UUID(str(selected_track["track_id"])) if isinstance(selected_track, dict) else None
        ),
        music_mix=music_mode if isinstance(selected_track, dict) else "none",
    )
    return validate_edit_plan(
        plan.model_dump(mode="json"),
        assets,
        creative_direction={
            "target_duration_seconds": target_duration_seconds,
            "edit_style": edit_style,
            "music_mode": music_mode,
        },
        music_tracks=music_tracks,
    )
