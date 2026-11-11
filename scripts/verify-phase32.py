#!/usr/bin/env python3
"""Read-only Phase 32B effect-registry check; no render or model request."""

import json
from pathlib import Path
import runpy
import sys


def main():
    request = runpy.run_path(str(Path(__file__).with_name("verify-phase14.py")))["request"]
    registry = request("effects/registry")
    effects = {effect.get("preset"): effect for effect in registry.get("effects", [])}
    if registry.get("version") != 1 or set(effects) != {"impact_frame", "clone_row"}:
        raise RuntimeError("deploy the Phase 32B native effects registry")
    expected = {
        "impact_frame": (0.1, 0.25, {"intensity"}),
        "clone_row": (0.1, 2.5, {"intensity", "position"}),
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
    print(json.dumps({
        "status": "passed",
        "registry_version": registry["version"],
        "effects": sorted(effects),
        "read_only": True,
        "renders_started": 0,
        "model_calls": 0,
        "note": "Synthetic and real-footage playback remain separate acceptance checks.",
    }, indent=2))
    print("PASS  Native effect registry is deployed; no editing work started.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Phase 32B verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
