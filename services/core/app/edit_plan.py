import hashlib
import json
import math
import re
from collections import defaultdict
from copy import deepcopy
from typing import Any, Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from app.take_quality import validate_story_content


EDIT_PLAN_SCHEMA_VERSION = "1.4"
MAX_PREVIEW_SECONDS = 60.0
MAX_CLIPS = 24
MAX_MONTAGE_CLIPS = 48
TARGET_DURATION_RANGES = {
    15: (12.0, 18.0),
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
        "rhythmic_punch",
    ] = "standard"
    story_role: Literal["hook", "context", "development", "payoff", "reaction", "ending"] = "development"
    editorial_intent: str = Field(default="", max_length=180)

    @model_validator(mode="after")
    def source_range_is_forward(self) -> "EditClip":
        if self.source_out - self.source_in < 0.25:
            raise ValueError("each clip must be at least 0.25 seconds long")
        return self


class CreativeEffectCue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: UUID
    start_seconds: float = Field(ge=0, le=60)
    duration_seconds: float = Field(ge=0.1, le=8.0)
    position: Literal["top", "center", "bottom", "full_frame"] = "bottom"
    intensity: Literal["subtle", "standard", "strong"] = "subtle"
    purpose: Literal["hook", "transition", "emphasis", "reveal", "reaction", "payoff"] = "emphasis"


class BrollCue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: UUID
    media_kind: Literal["video", "image"]
    source_in: float = Field(ge=0)
    source_out: float = Field(ge=0)
    start_seconds: float = Field(ge=0, le=60)
    duration_seconds: float = Field(ge=0.5, le=4)
    editorial_intent: str = Field(min_length=1, max_length=180)


class _CompatibleEditPlan(BaseModel):
    @model_serializer(mode="wrap")
    def serialize_legacy_plan(self, handler: Any) -> dict[str, Any]:
        document = handler(self)
        if document.get("schema_version") != "1.4" and not document.get("broll"):
            document.pop("broll", None)
        return document


class TalkingHeadEditPlan(_CompatibleEditPlan):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0", "1.1", "1.2", "1.3", "1.4"]
    recipe: Literal["talking_head"]
    clips: list[EditClip] = Field(min_length=1, max_length=MAX_CLIPS)
    caption_style: Literal["clean_blue_v1"]
    audio_preset: Literal["spoken_voice_v1"]
    end_card: Literal["none"]
    editorial_summary: str = Field(min_length=1, max_length=600)
    post_copy: str = Field(default="", max_length=2200)
    music_track_id: UUID | None = None
    music_mix: Literal["none", "subtle", "present"] = "none"
    caption_position: Literal["lower_safe", "middle", "upper"] = "lower_safe"
    caption_timing_offset_seconds: float = Field(default=0.0, ge=-0.5, le=0.5)
    effects: list[CreativeEffectCue] = Field(default_factory=list, max_length=8)
    broll: list[BrollCue] = Field(default_factory=list, max_length=8)


class MontageClip(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: UUID
    media_kind: Literal["video", "image"]
    source_in: float = Field(ge=0)
    source_out: float = Field(ge=0)
    duration: float = Field(ge=0.5, le=8.0)
    crop: Literal["center_fill"]
    transition: Literal["cut", "dip_to_black"] = "cut"
    visual_preset: Literal[
        "standard",
        "punch_in",
        "slow_push_in",
        "slow_pull_out",
        "rhythmic_punch",
    ] = "standard"
    include_source_audio: bool = False
    source_audio_gain_db: float = Field(default=0.0, ge=-12.0, le=12.0)
    story_role: Literal["hook", "context", "development", "payoff", "reaction", "ending"] = "development"
    editorial_intent: str = Field(default="", max_length=180)


class MontageEditPlan(_CompatibleEditPlan):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0", "1.1", "1.2", "1.3", "1.4"]
    recipe: Literal["montage"]
    clips: list[MontageClip] = Field(min_length=2, max_length=MAX_MONTAGE_CLIPS)
    audio_preset: Literal["montage_mix_v1"]
    end_card: Literal["none"]
    editorial_summary: str = Field(min_length=1, max_length=600)
    post_copy: str = Field(default="", max_length=2200)
    music_track_id: UUID | None = None
    music_mix: Literal["none", "subtle", "present"] = "none"
    caption_position: Literal["lower_safe", "middle", "upper"] = "lower_safe"
    caption_timing_offset_seconds: float = Field(default=0.0, ge=-0.5, le=0.5)
    effects: list[CreativeEffectCue] = Field(default_factory=list, max_length=8)
    broll: list[BrollCue] = Field(default_factory=list, max_length=8)


EditPlan: TypeAlias = TalkingHeadEditPlan | MontageEditPlan


def edit_plan_duration(plan: EditPlan) -> float:
    if isinstance(plan, MontageEditPlan):
        return sum(float(clip.duration) for clip in plan.clips)
    return sum(float(clip.source_out - clip.source_in) for clip in plan.clips)


def derive_duration_variant(plan: EditPlan, target_seconds: int) -> EditPlan:
    """Return a deterministic prefix cut without asking an editor model again."""

    available = edit_plan_duration(plan)
    remaining = min(float(target_seconds), available)
    clips: list[Any] = []
    for source_clip in plan.clips:
        clip = source_clip.model_copy(deep=True)
        duration = (
            float(clip.duration)
            if isinstance(plan, MontageEditPlan)
            else float(clip.source_out - clip.source_in)
        )
        minimum = 0.5 if isinstance(plan, MontageEditPlan) else 0.25
        if remaining < minimum:
            break
        used = min(duration, remaining)
        if isinstance(plan, MontageEditPlan):
            clip.duration = used
            if clip.media_kind == "video":
                clip.source_out = clip.source_in + used
        else:
            clip.source_out = clip.source_in + used
        if not clips:
            clip.transition = "cut"
        clips.append(clip)
        remaining -= used
        if remaining < minimum:
            break
    if isinstance(plan, MontageEditPlan) and len(clips) < 2:
        raise ValueError("a montage duration variant requires at least two source clips")
    if not clips:
        raise ValueError("the approved edit does not contain enough material for this duration")
    variant_duration = sum(
        float(clip.duration) if isinstance(plan, MontageEditPlan) else float(clip.source_out - clip.source_in)
        for clip in clips
    )
    effects = []
    for source_cue in plan.effects:
        if source_cue.start_seconds >= variant_duration:
            continue
        cue = source_cue.model_copy(deep=True)
        cue.duration_seconds = min(cue.duration_seconds, variant_duration - cue.start_seconds)
        if cue.duration_seconds >= 0.1:
            effects.append(cue)
    broll = []
    for source_cue in plan.broll:
        duration = min(source_cue.duration_seconds, variant_duration - source_cue.start_seconds)
        if duration >= 0.5:
            updates = {"duration_seconds": duration}
            if source_cue.media_kind == "video":
                updates["source_out"] = source_cue.source_in + duration
            broll.append(source_cue.model_copy(update=updates, deep=True))
    return plan.model_copy(update={"clips": clips, "effects": effects, "broll": broll}, deep=True)


def source_word_gaps(
    asset: dict[str, Any], source_in: float, source_out: float
) -> list[tuple[float, float, float]]:
    """Return spoken-word gaps fully contained in one selected source range."""

    words: list[tuple[float, float]] = []
    for segment in asset.get("transcript_segments", []):
        if not isinstance(segment, dict):
            continue
        for word in segment.get("words", []):
            if not isinstance(word, dict):
                continue
            try:
                start = float(word["start"])
                end = float(word["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if end > source_in and start < source_out and end > start:
                words.append((max(source_in, start), min(source_out, end)))
    words.sort()
    if not words:
        return []
    gaps: list[tuple[float, float, float]] = []
    if words[0][0] > source_in:
        gaps.append((source_in, words[0][0], words[0][0] - source_in))
    previous_end: float | None = None
    for start, end in words:
        if previous_end is not None and start > previous_end:
            gaps.append((previous_end, start, start - previous_end))
        previous_end = max(previous_end or end, end)
    if previous_end is not None and source_out > previous_end:
        gaps.append((previous_end, source_out, source_out - previous_end))
    return gaps


def _tighten_clip_pauses(
    plan: EditPlan,
    clip: Any,
    asset: dict[str, Any],
    max_pause_seconds: float,
) -> list[Any]:
    gaps = [
        gap
        for gap in source_word_gaps(asset, float(clip.source_in), float(clip.source_out))
        if gap[2] > max_pause_seconds + 0.08
    ]
    if not gaps:
        return [clip]

    minimum = 0.5 if isinstance(plan, MontageEditPlan) else 0.25
    source_in = float(clip.source_in)
    source_out = float(clip.source_out)
    leading = next((gap for gap in gaps if gap[0] == source_in), None)
    trailing = next((gap for gap in gaps if gap[1] == source_out), None)
    if leading is not None:
        source_in = max(source_in, leading[1] - max_pause_seconds)
    if trailing is not None:
        source_out = min(source_out, trailing[0] + max_pause_seconds)
    internal_gaps = [
        gap for gap in gaps if gap[0] > float(clip.source_in) and gap[1] < float(clip.source_out)
    ]
    ranges: list[tuple[float, float]] = []
    range_start = source_in
    for gap_start, gap_end, _duration in internal_gaps:
        left_end = gap_start + max_pause_seconds / 2
        right_start = gap_end - max_pause_seconds / 2
        if left_end - range_start < minimum:
            continue
        if source_out - right_start < minimum:
            continue
        ranges.append((range_start, left_end))
        range_start = right_start
    ranges.append((range_start, source_out))
    if len(ranges) == 1 and ranges[0] == (float(clip.source_in), float(clip.source_out)):
        return [clip]

    result: list[Any] = []
    for index, (source_in, source_out) in enumerate(ranges):
        candidate = clip.model_copy(deep=True)
        candidate.source_in = round(source_in, 3)
        candidate.source_out = round(source_out, 3)
        if index > 0:
            candidate.transition = "cut"
        if isinstance(plan, MontageEditPlan):
            candidate.duration = round(source_out - source_in, 3)
        result.append(candidate)
    return result


def apply_timeline_adjustments(
    plan: EditPlan,
    adjustments: list[dict[str, Any]],
    assets: list[dict[str, Any]] | None = None,
) -> EditPlan:
    """Apply review-screen changes to a persisted plan without a model call."""

    clips = [clip.model_copy(deep=True) for clip in plan.clips]
    handles = [clip_handle(index, clip.model_dump(mode="json")) for index, clip in enumerate(plan.clips)]
    # Keep each retained piece tied to its original timeline occurrence. Asset
    # IDs alone cannot distinguish two uses of the same source in one edit.
    origins: list[tuple[float, Any]] = []
    original_time = 0.0
    for clip in plan.clips:
        origins.append((original_time, clip))
        original_time += float(clip.duration if isinstance(plan, MontageEditPlan)
                               else clip.source_out - clip.source_in)
    inventory = {str(asset["asset_id"]): asset for asset in assets or []}
    for adjustment in adjustments:
        index = int(adjustment["clip_index"])
        handle = adjustment.get("clip_id")
        if handle:
            if handle not in handles:
                raise ValueError("the selected clip changed; refresh the review before editing")
            index = handles.index(handle)
        if index < 0 or index >= len(clips):
            raise ValueError(f"clip {index + 1} is no longer present in this edit")
        action = str(adjustment.get("action") or "keep")
        if action == "remove":
            clips.pop(index)
            origins.pop(index)
            handles.pop(index)
            continue
        if action == "move_up" and index > 0:
            clips[index - 1], clips[index] = clips[index], clips[index - 1]
            origins[index - 1], origins[index] = origins[index], origins[index - 1]
            handles[index - 1], handles[index] = handles[index], handles[index - 1]
            index -= 1
        elif action == "move_down" and index < len(clips) - 1:
            clips[index + 1], clips[index] = clips[index], clips[index + 1]
            origins[index + 1], origins[index] = origins[index], origins[index + 1]
            handles[index + 1], handles[index] = handles[index], handles[index + 1]
            index += 1
        if adjustment.get("replacement_asset_id"):
            replacement_id = str(adjustment["replacement_asset_id"])
            if replacement_id not in inventory:
                raise ValueError("replacement take must belong to this job")
            clips[index].asset_id = UUID(replacement_id)
        if adjustment.get("source_in") is not None:
            clips[index].source_in = float(adjustment["source_in"])
        if adjustment.get("source_out") is not None:
            clips[index].source_out = float(adjustment["source_out"])
        if adjustment.get("source_in") is not None or adjustment.get("source_out") is not None:
            if isinstance(plan, MontageEditPlan):
                clips[index].duration = round(clips[index].source_out - clips[index].source_in, 3)
        if adjustment.get("replacement_asset_id"):
            origins[index] = (origins[index][0], clips[index].model_copy(deep=True))
        if adjustment.get("split_at") is not None:
            split = float(adjustment["split_at"])
            clip = clips[index]
            minimum = .5 if isinstance(plan, MontageEditPlan) else .25
            if not clip.source_in + minimum <= split <= clip.source_out - minimum:
                raise ValueError("split must leave a valid source range on both sides")
            left, right = clip.model_copy(deep=True), clip.model_copy(deep=True)
            left.source_out, right.source_in, right.transition = split, split, "cut"
            if isinstance(plan, MontageEditPlan):
                left.duration, right.duration = split-left.source_in, right.source_out-split
            clips[index:index+1] = [left, right]
            origins[index:index+1] = [origins[index], origins[index]]
            handles[index:index+1] = [handles[index], handles[index] + ":split"]
        visual_preset = adjustment.get("visual_preset")
        if visual_preset is not None:
            clips[index].visual_preset = visual_preset
        audio_gain = adjustment.get("source_audio_gain_db")
        if audio_gain is not None:
            if not isinstance(plan, MontageEditPlan):
                raise ValueError("per-clip source volume is available for montages")
            clips[index].source_audio_gain_db = float(audio_gain)
            clips[index].include_source_audio = True
        max_pause = adjustment.get("max_pause_seconds")
        if max_pause is not None:
            asset = inventory.get(str(clips[index].asset_id))
            if asset is None:
                raise ValueError("source transcript timing is unavailable for this clip")
            tightened = _tighten_clip_pauses(plan, clips[index], asset, float(max_pause))
            maximum = MAX_MONTAGE_CLIPS if isinstance(plan, MontageEditPlan) else MAX_CLIPS
            if len(clips) - 1 + len(tightened) > maximum:
                raise ValueError("tightening pauses would create too many timeline clips")
            clips[index:index + 1] = tightened
            origins[index:index + 1] = [origins[index]] * len(tightened)
            handles[index:index + 1] = [handles[index] + f":{n}" for n in range(len(tightened))]
    minimum = 2 if isinstance(plan, MontageEditPlan) else 1
    if len(clips) < minimum:
        raise ValueError(f"this edit must keep at least {minimum} clip{'s' if minimum > 1 else ''}")
    clips[0].transition = "cut"
    # Map cues only through content that survives. Cues inside a removed pause
    # or deleted clip disappear; a cue at a new cut is clipped at that cut.
    # Adjacent unchanged pieces merge so an existing cue can still span a cut.
    mapping: list[list[float]] = []
    new_time = 0.0
    for clip, (old_time, original_clip) in zip(clips, origins, strict=True):
        duration = float(clip.duration if isinstance(plan, MontageEditPlan)
                         else clip.source_out - clip.source_in)
        old_start = old_time + float(clip.source_in - original_clip.source_in)
        old_end = old_start + duration
        if mapping and abs(mapping[-1][1] - old_start) < 0.001:
            mapping[-1][1] = old_end
        else:
            mapping.append([old_start, old_end, new_time])
        new_time += duration
    effects = []
    for cue in plan.effects:
        for old_start, old_end, new_start in mapping:
            if old_start <= cue.start_seconds < old_end:
                duration = round(min(cue.duration_seconds, old_end - cue.start_seconds), 3)
                if duration >= 0.1:
                    effects.append(cue.model_copy(update={
                        "start_seconds": round(new_start + cue.start_seconds - old_start, 3),
                        "duration_seconds": duration,
                    }, deep=True))
                break
    broll = []
    for cue in plan.broll:
        for old_start, old_end, new_start in mapping:
            if old_start <= cue.start_seconds < old_end:
                duration = round(min(cue.duration_seconds, old_end - cue.start_seconds), 3)
                if duration >= 0.5:
                    updates = {"start_seconds": round(new_start + cue.start_seconds - old_start, 3),
                               "duration_seconds": duration}
                    if cue.media_kind == "video":
                        updates["source_out"] = cue.source_in + duration
                    broll.append(cue.model_copy(update=updates, deep=True))
                break
    return plan.model_copy(
        update={"clips": clips, "effects": effects, "broll": broll,
                "editorial_summary": (plan.editorial_summary[:540] + " Adjusted in the local editorial workspace.")},
        deep=True,
    )


def clip_handle(index: int, clip: dict[str, Any]) -> str:
    identity = [index, str(clip.get("asset_id")), float(clip.get("source_in", 0)), float(clip.get("source_out", 0))]
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:16]


# This schema is intentionally small and contains only Structured Outputs
# features supported by the Responses API. Every property is required and all
# objects reject unknown keys.
EFFECT_CUE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "asset_id": {"type": "string", "format": "uuid"},
        "start_seconds": {"type": "number", "minimum": 0, "maximum": 60},
        "duration_seconds": {"type": "number", "minimum": 0.1, "maximum": 8},
        "position": {"type": "string", "enum": ["top", "center", "bottom", "full_frame"]},
        "intensity": {"type": "string", "enum": ["subtle", "standard", "strong"]},
        "purpose": {"type": "string", "enum": ["hook", "transition", "emphasis", "reveal", "reaction", "payoff"]},
    },
    "required": ["asset_id", "start_seconds", "duration_seconds", "position", "intensity", "purpose"],
    "additionalProperties": False,
}

BROLL_CUE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "asset_id": {"type": "string", "format": "uuid"},
        "media_kind": {"type": "string", "enum": ["video", "image"]},
        "source_in": {"type": "number", "minimum": 0},
        "source_out": {"type": "number", "minimum": 0},
        "start_seconds": {"type": "number", "minimum": 0, "maximum": 60},
        "duration_seconds": {"type": "number", "minimum": 0.5, "maximum": 4},
        "editorial_intent": {"type": "string", "minLength": 1, "maxLength": 180},
    },
    "required": ["asset_id", "media_kind", "source_in", "source_out", "start_seconds", "duration_seconds", "editorial_intent"],
}

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
                            "rhythmic_punch",
                        ],
                    },
                    "story_role": {
                        "type": "string",
                        "enum": ["hook", "context", "development", "payoff", "reaction", "ending"],
                    },
                    "editorial_intent": {"type": "string", "maxLength": 180},
                },
                "required": [
                    "asset_id",
                    "source_in",
                    "source_out",
                    "crop",
                    "transition",
                    "visual_preset",
                    "story_role",
                    "editorial_intent",
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
        "caption_position": {"type": "string", "enum": ["lower_safe", "middle", "upper"]},
        "caption_timing_offset_seconds": {"type": "number", "minimum": -0.5, "maximum": 0.5},
        "effects": {"type": "array", "maxItems": 8, "items": EFFECT_CUE_JSON_SCHEMA},
        "broll": {"type": "array", "maxItems": 8, "items": BROLL_CUE_JSON_SCHEMA},
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
        "caption_position",
        "caption_timing_offset_seconds",
        "effects",
        "broll",
    ],
    "additionalProperties": False,
}


MONTAGE_EDIT_PLAN_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string", "enum": [EDIT_PLAN_SCHEMA_VERSION]},
        "recipe": {"type": "string", "enum": ["montage"]},
        "clips": {
            "type": "array",
            "minItems": 2,
            "maxItems": MAX_MONTAGE_CLIPS,
            "items": {
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string", "format": "uuid"},
                    "media_kind": {"type": "string", "enum": ["video", "image"]},
                    "source_in": {"type": "number", "minimum": 0},
                    "source_out": {"type": "number", "minimum": 0},
                    "duration": {"type": "number", "minimum": 0.5, "maximum": 8.0},
                    "crop": {"type": "string", "enum": ["center_fill"]},
                    "transition": {"type": "string", "enum": ["cut", "dip_to_black"]},
                    "visual_preset": {
                        "type": "string",
                        "enum": ["standard", "punch_in", "slow_push_in", "slow_pull_out", "rhythmic_punch"],
                    },
                    "include_source_audio": {"type": "boolean"},
                    "source_audio_gain_db": {
                        "type": "number",
                        "minimum": -12,
                        "maximum": 12,
                    },
                    "story_role": {
                        "type": "string",
                        "enum": ["hook", "context", "development", "payoff", "reaction", "ending"],
                    },
                    "editorial_intent": {"type": "string", "maxLength": 180},
                },
                "required": [
                    "asset_id",
                    "media_kind",
                    "source_in",
                    "source_out",
                    "duration",
                    "crop",
                    "transition",
                    "visual_preset",
                    "include_source_audio",
                    "source_audio_gain_db",
                    "story_role",
                    "editorial_intent",
                ],
                "additionalProperties": False,
            },
        },
        "audio_preset": {"type": "string", "enum": ["montage_mix_v1"]},
        "end_card": {"type": "string", "enum": ["none"]},
        "editorial_summary": {"type": "string", "minLength": 1, "maxLength": 600},
        "post_copy": {"type": "string", "maxLength": 2200},
        "music_track_id": {"type": ["string", "null"], "format": "uuid"},
        "music_mix": {"type": "string", "enum": ["none", "subtle", "present"]},
        "caption_position": {"type": "string", "enum": ["lower_safe", "middle", "upper"]},
        "caption_timing_offset_seconds": {"type": "number", "minimum": -0.5, "maximum": 0.5},
        "effects": {"type": "array", "maxItems": 8, "items": EFFECT_CUE_JSON_SCHEMA},
        "broll": {"type": "array", "maxItems": 8, "items": BROLL_CUE_JSON_SCHEMA},
    },
    "required": [
        "schema_version",
        "recipe",
        "clips",
        "audio_preset",
        "end_card",
        "editorial_summary",
        "post_copy",
        "music_track_id",
        "music_mix",
        "caption_position",
        "caption_timing_offset_seconds",
        "effects",
        "broll",
    ],
    "additionalProperties": False,
}


def schema_for_recipe(recipe: str) -> dict[str, Any]:
    if recipe == "montage":
        return MONTAGE_EDIT_PLAN_JSON_SCHEMA
    return EDIT_PLAN_JSON_SCHEMA


def document_sha256(document: dict[str, Any]) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def repair_predictable_plan_defaults(
    document: dict[str, Any],
    *,
    creative_direction: dict[str, Any] | None = None,
    music_tracks: list[dict[str, Any]] | None = None,
    creative_effects: list[dict[str, Any]] | None = None,
    previous_plan: dict[str, Any] | None = None,
    complete_creative_defaults: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    """Apply safe defaults that do not require another model decision."""

    repaired = deepcopy(document)
    repairs: list[str] = []
    if complete_creative_defaults and (creative_direction or {}).get("edit_style") in {"energetic", "high_impact"}:
        # Only complete newly generated plans. Exact re-renders and local
        # revisions keep their saved transitions. Never split or retime a cut.
        if repaired.get("recipe") == "talking_head":
            parsed = TalkingHeadEditPlan.model_validate(repaired)
            if (creative_direction or {}).get("edit_style") == "high_impact":
                for index, clip in enumerate(parsed.clips):
                    intentional_hold = clip.story_role == "reaction" or re.search(
                        r"\b(hold|steady|stable|breathe|no zoom|stay wide)\b", clip.editorial_intent, re.IGNORECASE)
                    if clip.visual_preset == "standard" and clip.source_out - clip.source_in >= 5 and not intentional_hold:
                        repaired["clips"][index]["visual_preset"] = "rhythmic_punch"
                        repairs.append("added_rhythmic_punch_without_changing_dialogue")
            if edit_plan_duration(parsed) >= 20 and len(parsed.clips) > 1 and all(
                clip.transition == "cut" for clip in parsed.clips
            ):
                boundaries = list(range(1, len(parsed.clips)))
                role_changes = [index for index in boundaries
                                if parsed.clips[index].story_role != parsed.clips[index - 1].story_role]
                candidates = role_changes or boundaries
                midpoint = edit_plan_duration(parsed) / 2
                boundary_times = [sum(clip.source_out - clip.source_in for clip in parsed.clips[:index])
                                  for index in candidates]
                chosen = min(zip(candidates, boundary_times), key=lambda item: abs(item[1] - midpoint))[0]
                repaired["clips"][chosen]["transition"] = "dip_to_black"
                repairs.append("added_required_transition_at_existing_story_boundary")
    requested_music = (creative_direction or {}).get("music_mode") or "none"
    if (creative_direction or {}).get("broll_enabled") is False and repaired.get("broll"):
        repaired["broll"] = []
        repairs.append("removed_broll_at_user_request")
    tracks = music_tracks or []
    if "effects" not in repaired:
        repaired["effects"] = []
    if (creative_direction or {}).get("effect_level", "off") == "off" and repaired.get("effects"):
        repaired["effects"] = []
        repairs.append("removed_unrequested_creative_effects")
    else:
        cues = repaired.get("effects")
        approved_effects = {str(item["asset_id"]) for item in creative_effects or []}
        maximum = {"subtle": 2, "social": 4, "meme_heavy": 8}.get(
            (creative_direction or {}).get("effect_level"), 0)
        if maximum and isinstance(cues, list) and all(
            isinstance(cue, dict) and str(cue.get("asset_id")) in approved_effects
            and isinstance(cue.get("start_seconds"), (int, float))
            and math.isfinite(cue["start_seconds"]) for cue in cues
        ):
            # An FX collision is not a reason to pay for a new story/cut list.
            # Keep the first approved cue at each beat; never invent a new cue.
            spaced: list[dict[str, Any]] = []
            for cue in sorted(cues, key=lambda item: item["start_seconds"]):
                if len(spaced) < maximum and (
                    not spaced or cue["start_seconds"] - spaced[-1]["start_seconds"] >= 0.5
                ):
                    spaced.append(cue)
            if len(spaced) != len(cues):
                repaired["effects"] = spaced
                repairs.append("reduced_effect_cue_collisions_without_changing_story")
    if requested_music == "none" and (
        repaired.get("music_track_id") is not None or repaired.get("music_mix") != "none"
    ):
        repaired["music_track_id"] = None
        repaired["music_mix"] = "none"
        repairs.append("removed_unrequested_music")
    elif requested_music in {"subtle", "present"} and tracks:
        approved_ids = {str(track["track_id"]) for track in tracks if track.get("track_id")}
        selected_id = repaired.get("music_track_id")
        preferred_track_id = (creative_direction or {}).get("selected_music_track_id")
        if preferred_track_id is not None and str(preferred_track_id) in approved_ids and str(selected_id or "") != str(preferred_track_id):
            repaired["music_track_id"] = str(preferred_track_id)
            repaired["music_mix"] = requested_music
            selected_id = str(preferred_track_id)
            repairs.append("applied_specifically_selected_music_track")
        if selected_id is None:
            previous_track_id = (previous_plan or {}).get("music_track_id")
            track_id = (
                preferred_track_id
                if preferred_track_id is not None and str(preferred_track_id) in approved_ids
                else previous_track_id
                if previous_track_id is not None and str(previous_track_id) in approved_ids
                else tracks[0].get("track_id")
            )
            if track_id:
                repaired["music_track_id"] = str(track_id)
                repaired["music_mix"] = requested_music
                repairs.append(
                    "preserved_previous_approved_music_track"
                    if previous_track_id is not None and str(previous_track_id) == str(track_id)
                    else "selected_first_approved_music_track"
                )
        elif str(selected_id) in approved_ids and repaired.get("music_mix") == "none":
            repaired["music_mix"] = requested_music
            repairs.append("matched_requested_music_mix")
    return repaired, repairs


def protect_spoken_boundaries(plan: EditPlan, assets: list[dict[str, Any]]) -> EditPlan:
    """Add small source-backed handles so audible clips do not shear words."""

    protected = plan.model_copy(deep=True)
    inventory = {str(asset["asset_id"]): asset for asset in assets}
    originals = {
        id(clip): (float(clip.source_in), float(clip.source_out))
        for clip in protected.clips
    }
    by_asset: dict[str, list[Any]] = defaultdict(list)

    for clip in protected.clips:
        if isinstance(protected, MontageEditPlan) and (
            clip.media_kind != "video" or not clip.include_source_audio
        ):
            continue
        asset_id = str(clip.asset_id)
        asset = inventory.get(asset_id)
        if asset is None:
            continue
        by_asset[asset_id].append(clip)
        words: list[tuple[float, float]] = []
        for segment in asset.get("transcript_segments", []):
            if not isinstance(segment, dict):
                continue
            for word in segment.get("words", []):
                if not isinstance(word, dict):
                    continue
                try:
                    start = float(word["start"])
                    end = float(word["end"])
                except (KeyError, TypeError, ValueError):
                    continue
                if end > float(clip.source_in) and start < float(clip.source_out):
                    words.append((start, end))
        if not words:
            continue
        words.sort()
        duration = float(asset.get("duration_seconds") or clip.source_out)
        clip.source_in = round(max(0.0, min(float(clip.source_in), words[0][0] - 0.12)), 3)
        clip.source_out = round(
            min(duration, max(float(clip.source_out), words[-1][1] + 0.16)), 3
        )

    # Adjacent selections from one source can both expand into the same silence.
    # Split that silence at the original midpoint while preserving invalid model
    # overlaps for the validator to report normally.
    for clips in by_asset.values():
        ordered = sorted(clips, key=lambda item: originals[id(item)][0])
        for left, right in zip(ordered, ordered[1:], strict=False):
            left_original = originals[id(left)]
            right_original = originals[id(right)]
            if left_original[1] <= right_original[0] and left.source_out > right.source_in:
                boundary = round((left_original[1] + right_original[0]) / 2, 3)
                left.source_out = boundary
                right.source_in = boundary

    if isinstance(protected, MontageEditPlan):
        for clip in protected.clips:
            if clip.media_kind == "video":
                clip.duration = round(float(clip.source_out - clip.source_in), 3)
    return protected


def _validate_broll(plan: EditPlan, assets: list[dict[str, Any]], duration: float, direction: dict[str, Any]) -> None:
    if direction.get("broll_enabled") is False:
        plan.broll = []
    if not plan.broll:
        return
    if plan.schema_version != "1.4":
        raise ValueError("B-roll overlays require edit-plan schema 1.4")
    if direction.get("edit_style") != "high_impact":
        raise ValueError("B-roll overlays require the High impact style")
    inventory = {str(asset["asset_id"]): asset for asset in assets}
    previous_end = 0.0
    covered = 0.0
    for cue in sorted(plan.broll, key=lambda item: item.start_seconds):
        if not all(math.isfinite(value) for value in (cue.source_in, cue.source_out, cue.start_seconds, cue.duration_seconds)):
            raise ValueError("B-roll timecodes must be finite")
        asset = inventory.get(str(cue.asset_id))
        if asset is None:
            raise ValueError("B-roll asset does not belong to this job")
        image = str(asset.get("mime_type") or "").startswith("image/")
        if cue.media_kind == "image":
            if not image or cue.source_in != 0 or cue.source_out != 0:
                raise ValueError("image B-roll requires an uploaded image and zero source timecodes")
        elif image or not asset.get("has_video") or abs(cue.source_out - cue.source_in - cue.duration_seconds) > 0.01:
            raise ValueError("video B-roll duration must match an uploaded video source range")
        elif cue.source_out > float(asset.get("duration_seconds") or 0) + 0.01:
            raise ValueError("B-roll source range exceeds the uploaded video")
        end = cue.start_seconds + cue.duration_seconds
        if cue.start_seconds < previous_end - 0.001 or end > duration + 0.01:
            raise ValueError("B-roll overlays cannot overlap or extend beyond the edit")
        previous_end = end
        covered += cue.duration_seconds
    if covered > duration * 0.6 + 0.01:
        raise ValueError("B-roll may cover at most 60 percent of the main story")


def _validate_effect_cues(
    plan: EditPlan,
    total_duration: float,
    direction: dict[str, Any],
    creative_effects: list[dict[str, Any]],
) -> None:
    level = str(direction.get("effect_level") or "off")
    limits = {"off": 0, "subtle": 2, "social": 4, "meme_heavy": 8}
    maximum = limits.get(level)
    if maximum is None:
        raise ValueError("the job contains an unsupported creative effect level")
    if level == "off":
        plan.effects = []
        return
    if len(plan.effects) > maximum:
        raise ValueError(f"the {level} effect level permits at most {maximum} cues")
    inventory = {str(item["asset_id"]): item for item in creative_effects}
    previous_start = -10.0
    for cue in sorted(plan.effects, key=lambda item: item.start_seconds):
        item = inventory.get(str(cue.asset_id))
        if item is None:
            raise ValueError(f"creative asset {cue.asset_id} is not in the approved library")
        if cue.start_seconds + cue.duration_seconds > total_duration + 0.01:
            raise ValueError("a creative effect extends beyond the edit timeline")
        if cue.purpose != item.get("purpose"):
            raise ValueError("a creative effect cue must preserve its reviewed purpose")
        if cue.start_seconds - previous_start < 0.5:
            raise ValueError("creative effect cues must be at least 0.5 seconds apart")
        if level == "subtle" and cue.intensity == "strong":
            raise ValueError("strong creative effects are not allowed in subtle mode")
        previous_start = cue.start_seconds


def validate_edit_plan(
    document: dict[str, Any],
    assets: list[dict[str, Any]],
    *,
    allow_post_copy: bool = False,
    creative_direction: dict[str, Any] | None = None,
    music_tracks: list[dict[str, Any]] | None = None,
    creative_effects: list[dict[str, Any]] | None = None,
    enforce_story_quality: bool = False,
) -> EditPlan:
    if document.get("recipe") == "montage":
        return validate_montage_plan(
            document,
            assets,
            allow_post_copy=allow_post_copy,
            creative_direction=creative_direction,
            music_tracks=music_tracks,
            creative_effects=creative_effects,
        )
    plan = protect_spoken_boundaries(TalkingHeadEditPlan.model_validate(document), assets)
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
        _preferred_minimum, maximum = TARGET_DURATION_RANGES[target]
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
    if style in {"energetic", "high_impact"} and total_duration >= 8 and visual_emphasis_count == 0:
        raise ValueError("the energetic style requires at least one bounded visual emphasis")
    if style in {"energetic", "high_impact"} and total_duration >= 20 and transition_count == 0:
        raise ValueError("an energetic edit of 20 seconds or longer requires a transition beat")

    tracks = {str(track["track_id"]): track for track in music_tracks or []}
    requested_music = direction.get("music_mode") or "none"
    # The job setting is authoritative. Models and legacy saved plans may carry
    # a stale track selection, but a voice-only job must always remain voice-only.
    if requested_music == "none":
        plan.music_track_id = None
        plan.music_mix = "none"
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
        selected_track_id = direction.get("selected_music_track_id")
        if selected_track_id and track_id != str(selected_track_id):
            raise ValueError("the edit plan did not use the specifically selected music track")

    _validate_effect_cues(plan, total_duration, direction, creative_effects or [])
    _validate_broll(plan, assets, total_duration, direction)

    for asset_id, asset_ranges in ranges.items():
        ordered = sorted(asset_ranges)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current[0] < previous[1] - 0.01:
                raise ValueError(f"asset {asset_id} contains overlapping source ranges")

    policy = direction.get("editorial_policy") or {}
    if enforce_story_quality:
        validate_story_content(plan, assets, policy)
        if policy.get("promotional") and not policy.get("bloopers_requested") and not policy.get("preserve_pauses_requested"):
            tightened = apply_timeline_adjustments(plan, [
                {"clip_index": index, "max_pause_seconds": 0.6}
                for index in reversed(range(len(plan.clips)))
            ], assets)
            for clip in tightened.clips:
                if clip.source_out - clip.source_in < 2 and clip.visual_preset in {"slow_push_in", "slow_pull_out"}:
                    clip.visual_preset = "punch_in"
            tightened.editorial_summary = plan.editorial_summary
            tightened_document, _ = repair_predictable_plan_defaults(
                tightened.model_dump(mode="json"), creative_direction=creative_direction,
                music_tracks=music_tracks, creative_effects=creative_effects)
            return validate_edit_plan(tightened_document, assets,
                allow_post_copy=allow_post_copy, creative_direction=creative_direction,
                music_tracks=music_tracks, creative_effects=creative_effects)
    return plan


def validate_montage_plan(
    document: dict[str, Any],
    assets: list[dict[str, Any]],
    *,
    allow_post_copy: bool = False,
    creative_direction: dict[str, Any] | None = None,
    music_tracks: list[dict[str, Any]] | None = None,
    creative_effects: list[dict[str, Any]] | None = None,
) -> MontageEditPlan:
    parsed_plan = MontageEditPlan.model_validate(document)
    # Validate the model's declared source timing before adding speech handles.
    # The handle pass deliberately keeps duration aligned with its adjusted
    # source range, so performing this check afterwards would silently repair
    # an invalid plan instead of rejecting it for bounded plan repair.
    for clip in parsed_plan.clips:
        if clip.media_kind != "video":
            continue
        source_duration = float(clip.source_out - clip.source_in)
        if abs(source_duration - float(clip.duration)) > 0.05:
            raise ValueError("video montage duration must match its source time range")
    plan = protect_spoken_boundaries(parsed_plan, assets)
    if plan.post_copy and not allow_post_copy:
        raise ValueError("AI-written post copy was not enabled for this project")
    inventory = {str(asset["asset_id"]): asset for asset in assets}
    total_duration = 0.0
    used_ranges: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for index, clip in enumerate(plan.clips):
        asset_id = str(clip.asset_id)
        asset = inventory.get(asset_id)
        if asset is None:
            raise ValueError(f"asset {asset_id} does not belong to this job")
        is_image = str(asset.get("mime_type") or "").startswith("image/")
        if clip.media_kind == "image":
            if not is_image:
                raise ValueError(f"asset {asset_id} is not an image source")
            if clip.source_in != 0 or clip.source_out != 0:
                raise ValueError("image montage clips must use zero source timecodes")
            if clip.include_source_audio:
                raise ValueError("image montage clips cannot include source audio")
            if abs(clip.source_audio_gain_db) > 0.001:
                raise ValueError("image montage clips cannot apply source audio gain")
        else:
            if is_image or not asset.get("has_video"):
                raise ValueError(f"asset {asset_id} is not a video source")
            source_duration = clip.source_out - clip.source_in
            if source_duration < 0.5:
                raise ValueError("video montage clips must be at least 0.5 seconds long")
            if abs(source_duration - clip.duration) > 0.05:
                raise ValueError("video montage duration must match its source time range")
            available = float(asset.get("duration_seconds") or 0)
            if clip.source_out > available + 0.01:
                raise ValueError(
                    f"asset {asset_id} ends at {available:.3f}s, before requested "
                    f"source_out {clip.source_out:.3f}s"
                )
            if clip.include_source_audio and not asset.get("has_audio"):
                raise ValueError(f"asset {asset_id} has no source audio")
            if not clip.include_source_audio and abs(clip.source_audio_gain_db) > 0.001:
                raise ValueError("muted montage clips cannot apply source audio gain")
            used_ranges[asset_id].append((clip.source_in, clip.source_out))
        if index == 0 and clip.transition != "cut":
            raise ValueError("the first montage clip must begin with a cut")
        total_duration += clip.duration

    if total_duration > MAX_PREVIEW_SECONDS + 0.01:
        raise ValueError(f"preview duration {total_duration:.3f}s exceeds 60 seconds")
    direction = creative_direction or {}
    target = direction.get("target_duration_seconds")
    if target in TARGET_DURATION_RANGES:
        _preferred_minimum, maximum = TARGET_DURATION_RANGES[target]
        if total_duration > maximum + 0.01:
            raise ValueError(
                f"montage duration {total_duration:.3f}s exceeds the {maximum:.3f}s ceiling "
                f"for a {target}s target"
            )
    for asset_id, ranges in used_ranges.items():
        ordered = sorted(ranges)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current[0] < previous[1] - 0.01:
                raise ValueError(f"asset {asset_id} contains overlapping source ranges")

    tracks = {str(track["track_id"]): track for track in music_tracks or []}
    requested_music = direction.get("music_mode") or "none"
    # Enforce the same job-level invariant for montage plans, including older
    # plans retried after the music preference changed.
    if requested_music == "none":
        plan.music_track_id = None
        plan.music_mix = "none"
    if plan.music_track_id is None:
        if plan.music_mix != "none":
            raise ValueError("a music mix requires an approved music track")
        if requested_music != "none" and tracks:
            raise ValueError("this montage requested music but did not select a track")
    else:
        track_id = str(plan.music_track_id)
        if requested_music == "none":
            raise ValueError("music was not enabled for this montage")
        if track_id not in tracks:
            raise ValueError(f"music track {track_id} is not in the approved library")
        if plan.music_mix != requested_music:
            raise ValueError("the music mix does not match the job's requested music level")
        selected_track_id = direction.get("selected_music_track_id")
        if selected_track_id and track_id != str(selected_track_id):
            raise ValueError("the montage did not use the specifically selected music track")
    _validate_effect_cues(plan, total_duration, direction, creative_effects or [])
    _validate_broll(plan, assets, total_duration, direction)
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
    if edit_style in {"energetic", "high_impact"} and duration >= 4:
        split = round(duration / 2, 3)
        clips = [
            EditClip(
                asset_id=UUID(str(asset["asset_id"])),
                source_in=0.0,
                source_out=split,
                crop="center_fill",
                transition="cut",
                visual_preset="standard",
                story_role="hook",
                editorial_intent="Open with the source and establish the subject.",
            ),
            EditClip(
                asset_id=UUID(str(asset["asset_id"])),
                source_in=split,
                source_out=round(duration, 3),
                crop="center_fill",
                transition="dip_to_black",
                visual_preset="punch_in",
                story_role="ending",
                editorial_intent="Finish the selected thought with visual emphasis.",
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
                story_role="hook",
                editorial_intent="Carry the complete source thought from opening to finish.",
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


def deterministic_montage_plan(
    assets: list[dict[str, Any]],
    target_duration_seconds: int | None,
    edit_style: str,
    music_mode: str,
    music_tracks: list[dict[str, Any]] | None,
) -> MontageEditPlan:
    eligible = [
        asset
        for asset in assets
        if asset.get("has_video") or str(asset.get("mime_type") or "").startswith("image/")
    ]
    if not eligible:
        raise ValueError("the montage recipe needs at least one video or image")
    requested_target = float(target_duration_seconds or 30)
    has_still = any(
        str(asset.get("mime_type") or "").startswith("image/") for asset in eligible
    )
    available_video = sum(
        float(asset.get("duration_seconds") or 0)
        for asset in eligible
        if asset.get("has_video")
    )
    target = requested_target if has_still else min(requested_target, available_video)
    if target < 1.0:
        raise ValueError("the montage recipe needs at least one second of usable source media")
    clip_count = min(
        MAX_MONTAGE_CLIPS,
        max(2, math.ceil(target / 8), round(target / 3)),
    )
    clip_duration = round(target / clip_count, 3)
    clips: list[MontageClip] = []
    video_offsets: dict[str, float] = defaultdict(float)
    candidate_index = 0
    total_duration = 0.0
    attempts = 0
    while total_duration < target - 0.01 and len(clips) < MAX_MONTAGE_CLIPS:
        attempts += 1
        if attempts > MAX_MONTAGE_CLIPS * max(2, len(eligible)):
            break
        asset = eligible[candidate_index % len(eligible)]
        candidate_index += 1
        asset_id = str(asset["asset_id"])
        is_image = str(asset.get("mime_type") or "").startswith("image/")
        duration = min(clip_duration, target - total_duration)
        if is_image:
            source_in = source_out = 0.0
        else:
            available = float(asset.get("duration_seconds") or 0)
            source_in = video_offsets[asset_id]
            duration = min(duration, available - source_in)
            source_out = source_in + duration
            duration = round(source_out - source_in, 3)
            if duration < 0.5:
                continue
            video_offsets[asset_id] = source_out
        index = len(clips)
        clips.append(
            MontageClip(
                asset_id=UUID(asset_id),
                media_kind="image" if is_image else "video",
                source_in=round(source_in, 3),
                source_out=round(source_out, 3),
                duration=duration,
                crop="center_fill",
                transition="dip_to_black" if index and index % 4 == 0 else "cut",
                visual_preset=(
                    "slow_push_in"
                    if is_image
                    else "punch_in"
                    if edit_style in {"energetic", "high_impact"} and index % 3 == 1
                    else "standard"
                ),
                include_source_audio=bool(asset.get("has_audio")) and index % 5 == 0,
                source_audio_gain_db=0.0,
            )
        )
        total_duration += duration
    if len(clips) < 2:
        raise ValueError("the montage recipe needs enough source media for at least two shots")
    for index, clip in enumerate(clips):
        if index == 0:
            clip.story_role = "hook"
            clip.editorial_intent = "Open on a strong source-backed image or action."
        elif index == len(clips) - 1:
            clip.story_role = "ending"
            clip.editorial_intent = "Resolve the sequence on a clear final source moment."
        elif index >= max(1, len(clips) - 2):
            clip.story_role = "payoff"
            clip.editorial_intent = "Deliver or support the strongest moment in the sequence."
        elif index == 1:
            clip.story_role = "context"
            clip.editorial_intent = "Orient the viewer after the opening beat."
        else:
            clip.story_role = "development"
            clip.editorial_intent = "Build the visual sequence with new source evidence."
    selected_track = (music_tracks or [None])[0] if music_mode != "none" else None
    plan = MontageEditPlan(
        schema_version=EDIT_PLAN_SCHEMA_VERSION,
        recipe="montage",
        clips=clips,
        audio_preset="montage_mix_v1",
        end_card="none",
        editorial_summary="Local-only source-led montage assembled from eligible media.",
        post_copy="",
        music_track_id=UUID(str(selected_track["track_id"])) if isinstance(selected_track, dict) else None,
        music_mix=music_mode if isinstance(selected_track, dict) else "none",
    )
    return validate_montage_plan(
        plan.model_dump(mode="json"),
        assets,
        creative_direction={
            "target_duration_seconds": target_duration_seconds,
            "edit_style": edit_style,
            "music_mode": music_mode,
        },
        music_tracks=music_tracks,
    )
