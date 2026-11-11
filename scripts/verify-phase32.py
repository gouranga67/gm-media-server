#!/usr/bin/env python3
"""Read-only Phase 32D effect-registry check; no render or model request."""

import json
from pathlib import Path
import runpy
import sys


def main():
    request = runpy.run_path(str(Path(__file__).with_name("verify-phase14.py")))["request"]
    registry = request("effects/registry")
    effects = {effect.get("preset"): effect for effect in registry.get("effects", [])}
    if registry.get("version") != 3 or set(effects) != {"impact_frame", "clone_row", "live_cursor", "letter_dive"}:
        raise RuntimeError("deploy the Phase 32D native effects registry")
    expected = {
        "impact_frame": (0.1, 0.25, {"intensity"}),
        "clone_row": (0.1, 2.5, {"intensity", "position"}),
        "live_cursor": (0.4, 4.0, {"intensity", "cursor_start_x", "cursor_start_y", "cursor_end_x", "cursor_end_y", "click"}),
        "letter_dive": (0.6, 2.5, {"intensity", "position", "letter_text"}),
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
    if cursor["click"].get("type") != "boolean" or cursor["click"].get("default") is not True:
        raise RuntimeError("the Live Cursor click contract is incomplete")
    print(json.dumps({
        "status": "passed",
        "registry_version": registry["version"],
        "effects": sorted(effects),
        "read_only": True,
        "renders_started": 0,
        "model_calls": 0,
        "note": "Synthetic and real-footage playback remain separate acceptance checks.",
    }, indent=2))
    print("PASS  Letter Dive registry contract is deployed; no editing work started.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Phase 32D verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
