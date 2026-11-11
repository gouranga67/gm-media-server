"""Versioned native-effect catalogue shared by validation, rendering and UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


EFFECT_REGISTRY_VERSION = 1


@dataclass(frozen=True)
class EffectParameter:
    key: str
    label: str
    values: tuple[str, ...]
    default: str

    def public(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "type": "enum",
            "values": list(self.values),
            "default": self.default,
        }


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
    values=("subtle", "standard", "strong"),
    default="standard",
)
POSITION = EffectParameter(
    key="position",
    label="Position",
    values=("upper", "center", "lower"),
    default="center",
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
        f"{descriptions}. Strength is subtle, standard or strong. Use only a listed position; "
        "effects preserve recorded dialogue and render below captions. "
    )
