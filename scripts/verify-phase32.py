#!/usr/bin/env python3
"""Read-only Phase 32J effect-registry check; no render or model request."""

import json
from pathlib import Path
import runpy
import sys


def main():
    request = runpy.run_path(str(Path(__file__).with_name("verify-phase14.py")))["request"]
    registry = request("effects/registry")
    effects = {effect.get("preset"): effect for effect in registry.get("effects", [])}
    if registry.get("version") != 9 or set(effects) != {"impact_frame", "clone_row", "live_cursor", "letter_dive", "comment_drop", "voice_note", "post_wall", "sketch_words", "rack_focus", "paper_tear"}:
        raise RuntimeError("deploy the Phase 32J native effects registry")
    expected = {
        "impact_frame": (0.1, 0.25, {"intensity"}),
        "clone_row": (0.1, 2.5, {"intensity", "position"}),
        "live_cursor": (0.4, 4.0, {"intensity", "cursor_start_x", "cursor_start_y", "cursor_end_x", "cursor_end_y", "click"}),
        "letter_dive": (0.6, 2.5, {"intensity", "position", "letter_text"}),
        "comment_drop": (1.0, 4.0, {"intensity", "position", "comment_text"}),
        "voice_note": (1.0, 5.0, {"intensity", "position"}),
        "post_wall": (1.2, 5.0, {"intensity", "post_texts"}),
        "sketch_words": (0.8, 3.0, {"intensity", "position", "sketch_text"}),
        "rack_focus": (1.0, 4.0, {"intensity", "focus_start_x", "focus_start_y", "focus_end_x", "focus_end_y"}),
        "paper_tear": (0.4, 1.0, {"intensity", "boundary_index", "tear_direction"}),
    }
    for preset, (minimum, maximum, parameter_keys) in expected.items():
        effect = effects[preset]
        parameters = {parameter.get("key"): parameter for parameter in effect.get("parameters", [])}
        if (
            effect.get("minimum_duration_seconds") != minimum
            or effect.get("maximum_duration_seconds") != maximum
            or not minimum <= effect.get("default_duration_seconds", -1) <= maximum
            or set(parameters) != parameter_keys
            or not effect.get("preserves_dialogue")
            or not effect.get("captions_above_effect")
            or effect.get("requires_segmentation")
        ):
            raise RuntimeError(f"the {preset} registry contract is incomplete")
        intensity = parameters["intensity"]
        if intensity.get("values") != ["subtle", "standard", "strong"] or intensity.get("default") != "standard":
            raise RuntimeError(f"the {preset} strength contract is incomplete")
    if effects["clone_row"]["parameters"][1].get("values") != ["upper", "center", "lower"]:
        raise RuntimeError("the Clone Row position contract is incomplete")
    cursor = {parameter["key"]: parameter for parameter in effects["live_cursor"]["parameters"]}
    expected_cursor = {
        "cursor_start_x": (0.08, 0.92, 0.25), "cursor_start_y": (0.1, 0.82, 0.4),
        "cursor_end_x": (0.08, 0.92, 0.75), "cursor_end_y": (0.1, 0.82, 0.4),
    }
    for key, (minimum, maximum, default) in expected_cursor.items():
        if cursor[key].get("type") != "number" or (cursor[key].get("minimum"), cursor[key].get("maximum"), cursor[key].get("default")) != (minimum, maximum, default):
            raise RuntimeError(f"the Live Cursor {key} contract is incomplete")
    letter_text = {parameter["key"]: parameter for parameter in effects["letter_dive"]["parameters"]}["letter_text"]
    if letter_text.get("type") != "text" or letter_text.get("minimum_length") != 1 or letter_text.get("maximum_length") != 18:
        raise RuntimeError("the Letter Dive text contract is incomplete")
    comment_text = {parameter["key"]: parameter for parameter in effects["comment_drop"]["parameters"]}["comment_text"]
    if comment_text.get("type") != "text" or comment_text.get("minimum_length") != 1 or comment_text.get("maximum_length") != 48:
        raise RuntimeError("the Comment Drop text contract is incomplete")
    if cursor["click"].get("type") != "boolean" or cursor["click"].get("default") is not True:
        raise RuntimeError("the Live Cursor click contract is incomplete")
    post_texts = {parameter["key"]: parameter for parameter in effects["post_wall"]["parameters"]}["post_texts"]
    if post_texts.get("type") != "text_list" or (post_texts.get("minimum_items"), post_texts.get("maximum_items"), post_texts.get("item_maximum_length")) != (2, 3, 42):
        raise RuntimeError("the Post Wall card contract is incomplete")
    sketch_text = {parameter["key"]: parameter for parameter in effects["sketch_words"]["parameters"]}["sketch_text"]
    if sketch_text.get("type") != "text" or sketch_text.get("minimum_length") != 1 or sketch_text.get("maximum_length") != 24:
        raise RuntimeError("the Sketch Words text contract is incomplete")
    focus = {parameter["key"]: parameter for parameter in effects["rack_focus"]["parameters"]}
    expected_focus = {
        "focus_start_x": (0.3, 0.7, 0.35), "focus_start_y": (0.18, 0.82, 0.35),
        "focus_end_x": (0.3, 0.7, 0.65), "focus_end_y": (0.18, 0.82, 0.55),
    }
    for key, (minimum, maximum, default) in expected_focus.items():
        if focus[key].get("type") != "number" or (focus[key].get("minimum"), focus[key].get("maximum"), focus[key].get("default")) != (minimum, maximum, default):
            raise RuntimeError(f"the Rack Focus {key} contract is incomplete")
    tear = {parameter["key"]: parameter for parameter in effects["paper_tear"]["parameters"]}
    if (tear["boundary_index"].get("minimum"), tear["boundary_index"].get("maximum"), tear["boundary_index"].get("default")) != (1, 47, 1):
        raise RuntimeError("the Paper Tear boundary contract is incomplete")
    if tear["tear_direction"].get("values") != ["left", "right"] or tear["tear_direction"].get("default") != "left":
        raise RuntimeError("the Paper Tear direction contract is incomplete")
    print(json.dumps({
        "status": "passed",
        "registry_version": registry["version"],
        "effects": sorted(effects),
        "read_only": True,
        "renders_started": 0,
        "model_calls": 0,
        "note": "Synthetic and real-footage playback remain separate acceptance checks.",
    }, indent=2))
    print("PASS  Paper Tear registry contract is deployed; no editing work started.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Phase 32J verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
