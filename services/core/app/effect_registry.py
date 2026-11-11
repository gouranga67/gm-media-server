"""Versioned native-effect catalogue shared by validation, rendering and UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


EFFECT_REGISTRY_VERSION = 6


@dataclass(frozen=True)
class EffectParameter:
    key: str
    label: str
    kind: str
    default: Any
    values: tuple[Any, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    minimum_length: int | None = None
    maximum_length: int | None = None
    minimum_items: int | None = None
    maximum_items: int | None = None
    item_maximum_length: int | None = None

    def public(self) -> dict[str, Any]:
        result = {
            "key": self.key,
            "label": self.label,
            "type": self.kind,
            "default": list(self.default) if self.kind == "text_list" else self.default,
        }
        if self.values:
            result["values"] = list(self.values)
        if self.minimum is not None:
            result["minimum"] = self.minimum
        if self.maximum is not None:
            result["maximum"] = self.maximum
        if self.minimum_length is not None:
            result["minimum_length"] = self.minimum_length
        if self.maximum_length is not None:
            result["maximum_length"] = self.maximum_length
        if self.minimum_items is not None:
            result["minimum_items"] = self.minimum_items
        if self.maximum_items is not None:
            result["maximum_items"] = self.maximum_items
        if self.item_maximum_length is not None:
            result["item_maximum_length"] = self.item_maximum_length
        return result


@dataclass(frozen=True)
class EffectDefinition:
    preset: str
    label: str
    summary: str
    category: str
    version: int
    minimum_duration_seconds: float
    maximum_duration_seconds: float
    default_duration_seconds: float
    parameters: tuple[EffectParameter, ...]
    preserves_dialogue: bool = True
    captions_above_effect: bool = True
    requires_segmentation: bool = False

    def parameter(self, key: str) -> EffectParameter | None:
        return next((item for item in self.parameters if item.key == key), None)

    def public(self) -> dict[str, Any]:
        return {
            "preset": self.preset,
            "label": self.label,
            "summary": self.summary,
            "category": self.category,
            "version": self.version,
            "minimum_duration_seconds": self.minimum_duration_seconds,
            "maximum_duration_seconds": self.maximum_duration_seconds,
            "default_duration_seconds": self.default_duration_seconds,
            "parameters": [item.public() for item in self.parameters],
            "preserves_dialogue": self.preserves_dialogue,
            "captions_above_effect": self.captions_above_effect,
            "requires_segmentation": self.requires_segmentation,
        }


INTENSITY = EffectParameter(
    key="intensity",
    label="Strength",
    kind="enum",
    values=("subtle", "standard", "strong"),
    default="standard",
)
POSITION = EffectParameter(
    key="position",
    label="Position",
    kind="enum",
    values=("upper", "center", "lower"),
    default="center",
)
CURSOR_START_X = EffectParameter("cursor_start_x", "Start horizontal", "number", 0.25, minimum=0.08, maximum=0.92)
CURSOR_START_Y = EffectParameter("cursor_start_y", "Start vertical", "number", 0.4, minimum=0.1, maximum=0.82)
CURSOR_END_X = EffectParameter("cursor_end_x", "End horizontal", "number", 0.75, minimum=0.08, maximum=0.92)
CURSOR_END_Y = EffectParameter("cursor_end_y", "End vertical", "number", 0.4, minimum=0.1, maximum=0.82)
CURSOR_CLICK = EffectParameter("click", "Click pulse", "boolean", True)
LETTER_TEXT = EffectParameter("letter_text", "Text", "text", "", minimum_length=1, maximum_length=18)
COMMENT_TEXT = EffectParameter("comment_text", "Comment", "text", "", minimum_length=1, maximum_length=48)
POST_TEXTS = EffectParameter(
    "post_texts", "Source-backed cards", "text_list", (),
    minimum_items=2, maximum_items=3, item_maximum_length=42,
)


EFFECT_DEFINITIONS = (
    EffectDefinition(
        preset="impact_frame",
        label="Impact frame",
        summary="A single accent border for a meaningful visual beat.",
        category="accent",
        version=1,
        minimum_duration_seconds=0.1,
        maximum_duration_seconds=0.25,
        default_duration_seconds=0.2,
        parameters=(INTENSITY,),
    ),
    EffectDefinition(
        preset="clone_row",
        label="Clone row",
        summary="Three live copies of the complete recorded shot; no person cutout.",
        category="layout",
        version=1,
        minimum_duration_seconds=0.1,
        maximum_duration_seconds=2.5,
        default_duration_seconds=2.0,
        parameters=(INTENSITY, POSITION),
    ),
    EffectDefinition(
        preset="live_cursor",
        label="Live cursor",
        summary="A pointer moves between two safe frame positions with an optional click pulse.",
        category="pointer",
        version=1,
        minimum_duration_seconds=0.4,
        maximum_duration_seconds=4.0,
        default_duration_seconds=1.5,
        parameters=(INTENSITY, CURSOR_START_X, CURSOR_START_Y, CURSOR_END_X, CURSOR_END_Y, CURSOR_CLICK),
    ),
    EffectDefinition(
        preset="letter_dive",
        label="Letter dive",
        summary="A short source-backed word or phrase drops in one letter at a time.",
        category="typography",
        version=1,
        minimum_duration_seconds=0.6,
        maximum_duration_seconds=2.5,
        default_duration_seconds=1.4,
        parameters=(INTENSITY, POSITION, LETTER_TEXT),
    ),
    EffectDefinition(
        preset="comment_drop",
        label="Comment drop",
        summary="A short source-backed comment card enters in a safe caption-aware band.",
        category="typography",
        version=1,
        minimum_duration_seconds=1.0,
        maximum_duration_seconds=4.0,
        default_duration_seconds=2.2,
        parameters=(INTENSITY, POSITION, COMMENT_TEXT),
    ),
    EffectDefinition(
        preset="voice_note",
        label="Voice note",
        summary="A voice-message card animates over the real recorded speech without changing its audio.",
        category="social",
        version=1,
        minimum_duration_seconds=1.0,
        maximum_duration_seconds=5.0,
        default_duration_seconds=2.6,
        parameters=(INTENSITY, POSITION),
    ),
    EffectDefinition(
        preset="post_wall",
        label="Post wall",
        summary="Two or three source-backed idea cards build into a staggered wall without fake social metadata.",
        category="social",
        version=1,
        minimum_duration_seconds=1.2,
        maximum_duration_seconds=5.0,
        default_duration_seconds=3.0,
        parameters=(INTENSITY, POST_TEXTS),
    ),
)

EFFECTS_BY_PRESET = {item.preset: item for item in EFFECT_DEFINITIONS}


def effect_definition(preset: str) -> EffectDefinition:
    try:
        return EFFECTS_BY_PRESET[preset]
    except KeyError as error:
        raise ValueError(f"unsupported native effect: {preset}") from error


def public_effect_registry() -> dict[str, Any]:
    return {
        "version": EFFECT_REGISTRY_VERSION,
        "effects": [item.public() for item in EFFECT_DEFINITIONS],
    }


def editor_effect_instruction() -> str:
    descriptions = "; ".join(
        f"{item.preset} ({item.minimum_duration_seconds:g}–"
        f"{item.maximum_duration_seconds:g}s): {item.summary}"
        for item in EFFECT_DEFINITIONS
    )
    return (
        f"Optional finishing.visual_beats from native effect registry v{EFFECT_REGISTRY_VERSION}: "
        f"{descriptions}. Strength is subtle, standard or strong. Use only the parameters listed for that effect; "
        "effects preserve recorded dialogue and render below captions. "
    )
