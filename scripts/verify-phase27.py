#!/usr/bin/env python3
"""Read-only context/blooper readiness; does not generate concepts or edit jobs."""

import json
from pathlib import Path
import runpy
import sys


def main():
    request = runpy.run_path(str(Path(__file__).with_name("verify-phase14.py")))["request"]
    capability = request("system").get("context_intelligence") or {}
    if capability.get("version") != 2 or capability.get("incident_bundle_version") != 2 or capability.get("additional_analysis_model_calls") != 0:
        raise RuntimeError("deploy the Phase 27 build before running this check")
    if not all(capability.get(k) for k in ("complete_attempt_and_response", "library_context_links", "manual_blooper_range_hints")):
        raise RuntimeError("the context intelligence contract is incomplete")
    library = request("concepts/library-status")
    if not isinstance(library.get("spoken_sources"), int):
        raise RuntimeError("the recorded library lookup is unavailable")
    modern = 0
    for session in request("concepts"):
        if session.get("status") != "ready" or session.get("coverage", {}).get("blooper_contract_version") != 2:
            continue
        for concept in session["concepts"]:
            script = concept["script"]
            if set(concept.get("incident_ids") or []) != {beat.get("incident_id") for beat in script}:
                raise RuntimeError("a saved modern blooper option lost its incident citations")
            if not all(beat.get("setup") and beat.get("incident") and beat.get("reaction") for beat in script):
                raise RuntimeError("a saved modern blooper option has incomplete evidence")
        modern += 1
    print(json.dumps({"status":"passed", "capability":capability, "library":library, "modern_saved_sessions":modern,
        "read_only":True, "generated_concepts":0, "created_jobs":0, "model_calls":0,
        "note":"Technical evidence checks do not establish humour or story quality; listen to fresh options."},indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Phase 27 verification failed: {error}",file=sys.stderr)
        raise SystemExit(1)
