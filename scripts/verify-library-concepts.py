#!/usr/bin/env python3
"""Read-only readiness/contract checks for library concepts; never calls a model."""
import importlib.util
import json
from pathlib import Path
from uuid import UUID


def main():
    spec = importlib.util.spec_from_file_location("concept_readiness_requests", Path(__file__).with_name("verify-phase16.py"))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    coverage = helper.request("concepts/library-status")
    for key in ("unique_sources", "catalogued_sources", "spoken_sources", "visually_indexed_sources", "still_processing"):
        if not isinstance(coverage.get(key), int) or coverage[key] < 0:
            raise RuntimeError(f"invalid library coverage: {key}")
    sessions = helper.request("concepts")
    if not isinstance(sessions, list):
        raise RuntimeError("concept history is not a list")
    ready = 0
    for session in sessions:
        UUID(session["id"])
        detail = helper.request(f"concepts/{session['id']}")
        if "inventory" in detail or detail["status"] not in ("pending", "generating", "ready", "failed"):
            raise RuntimeError("concept response leaked internal inventory or has invalid state")
        if detail["status"] == "ready":
            ready += 1
            if not 1 <= len(detail["concepts"]) <= 3:
                raise RuntimeError("ready concept session has invalid option count")
            for concept in detail["concepts"]:
                UUID(concept["id"])
                if not concept.get("source_backed") or not 2 <= len(concept["script"]) <= 10:
                    raise RuntimeError("concept does not declare its recorded source script")
                for beat in concept["script"]:
                    UUID(beat["asset_id"])
                    if not beat["text"] or not 0 <= beat["start"] < beat["end"]:
                        raise RuntimeError("invalid recorded speech citation")
    print(json.dumps({"status": "passed", "library": coverage, "saved_sessions": len(sessions), "ready_sessions": ready,
                      "generated_concepts": 0, "created_jobs": 0, "model_calls": 0}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"Library concept verification failed: {error}") from error
