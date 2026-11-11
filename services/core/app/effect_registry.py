"""Versioned native-effect catalogue shared by validation, rendering and UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


EFFECT_REGISTRY_VERSION = 11


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
    best_for: str
    avoid_when: str
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
            "best_for": self.best_for,
            "avoid_when": self.avoid_when,
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
SKETCH_TEXT = EffectParameter("sketch_text", "Words", "text", "", minimum_length=1, maximum_length=24)
FOCUS_START_X = EffectParameter("focus_start_x", "Start horizontal", "number", 0.35, minimum=0.3, maximum=0.7)
FOCUS_START_Y = EffectParameter("focus_start_y", "Start vertical", "number", 0.35, minimum=0.18, maximum=0.82)
FOCUS_END_X = EffectParameter("focus_end_x", "End horizontal", "number", 0.65, minimum=0.3, maximum=0.7)
FOCUS_END_Y = EffectParameter("focus_end_y", "End vertical", "number", 0.55, minimum=0.18, maximum=0.82)
TEAR_BOUNDARY_INDEX = EffectParameter("boundary_index", "Clip boundary", "number", 1, minimum=1, maximum=47)
TEAR_DIRECTION = EffectParameter(
    "tear_direction", "Pull direction", "enum", "left", values=("left", "right")
)
DOLLY_CLIP_INDEX = EffectParameter("dolly_clip_index", "Video clip", "number", 0, minimum=0, maximum=47)
DOLLY_DIRECTION = EffectParameter(
    "dolly_direction", "Move", "enum", "push_in", values=("push_in", "pull_out")
)
DOLLY_ANCHOR_X = EffectParameter("dolly_anchor_x", "Horizontal anchor", "number", 0.5, minimum=0.3, maximum=0.7)
DOLLY_ANCHOR_Y = EffectParameter("dolly_anchor_y", "Vertical anchor", "number", 0.5, minimum=0.25, maximum=0.75)


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
        best_for="One important beat, reveal or change that deserves a brief visual accent.",
        avoid_when="The moment is routine, visually busy or already uses another strong accent.",
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
        best_for="A short energetic talking-head beat where repeating the complete frame adds emphasis.",
        avoid_when="A person cutout is required, the frame is already crowded or captions need the full width.",
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
        best_for="Pointing to a real control, product detail or on-screen location.",
        avoid_when="The target moves, its position is uncertain or a click would imply an action that did not happen.",
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
        best_for="A genuine short word or phrase that should land with the spoken beat.",
        avoid_when="The wording is not supported by the footage or competes with important dialogue captions.",
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
        best_for="A faithful short reaction, observation or takeaway supported by the footage.",
        avoid_when="It would invent audience feedback, attribution or a claim not present in the source.",
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
        best_for="A real spoken passage that benefits from a familiar voice-message treatment.",
        avoid_when="There is no recorded speech in the range or the card would imply a sender who was not identified.",
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
        best_for="Two or three genuine ideas or faithful summaries that build together.",
        avoid_when="The cards would fabricate posts, accounts, engagement or unsupported wording.",
    ),
    EffectDefinition(
        preset="sketch_words",
        label="Sketch words",
        summary="One to three source-backed words draw on with marker-like lettering and accent strokes.",
        category="typography",
        version=1,
        minimum_duration_seconds=0.8,
        maximum_duration_seconds=3.0,
        default_duration_seconds=1.6,
        parameters=(INTENSITY, POSITION, SKETCH_TEXT),
        best_for="One to three genuine keywords that deserve a handmade emphasis.",
        avoid_when="The words are not source-backed, the scene is serious or the frame is already text-heavy.",
    ),
    EffectDefinition(
        preset="rack_focus",
        label="Rack focus",
        summary="A simulated sharp focus window moves across a softly blurred stable shot; no depth detection.",
        category="camera",
        version=1,
        minimum_duration_seconds=1.0,
        maximum_duration_seconds=4.0,
        default_duration_seconds=2.0,
        parameters=(INTENSITY, FOCUS_START_X, FOCUS_START_Y, FOCUS_END_X, FOCUS_END_Y),
        best_for="A stable shot with two clear visual targets and a deliberate change of attention.",
        avoid_when="The camera or subjects move heavily, depth realism is required or the targets are uncertain.",
    ),
    EffectDefinition(
        preset="paper_tear",
        label="Paper tear",
        summary="The outgoing clip tears away in staggered paper strips to reveal the next real clip.",
        category="transition",
        version=1,
        minimum_duration_seconds=0.4,
        maximum_duration_seconds=1.0,
        default_duration_seconds=0.7,
        parameters=(INTENSITY, TEAR_BOUNDARY_INDEX, TEAR_DIRECTION),
        best_for="A playful or tactile change between two clips joined by a clean ordinary cut.",
        avoid_when="There is no eligible cut, the moment is formal or another transition already defines the boundary.",
    ),
    EffectDefinition(
        preset="dolly_zoom",
        label="Dolly zoom",
        summary="A bounded crop-and-scale push or pull over one stable clip; no real camera parallax or depth reconstruction.",
        category="camera",
        version=1,
        minimum_duration_seconds=1.0,
        maximum_duration_seconds=8.0,
        default_duration_seconds=2.0,
        parameters=(INTENSITY, DOLLY_CLIP_INDEX, DOLLY_DIRECTION, DOLLY_ANCHOR_X, DOLLY_ANCHOR_Y),
        best_for="One complete stable shot where a restrained push or pull can heighten attention.",
        avoid_when="The shot already moves, uses tracked framing or picture layers, or needs real parallax or depth.",
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
