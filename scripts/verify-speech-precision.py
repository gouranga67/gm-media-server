#!/usr/bin/env python3
"""Read-only deployment and background speech-analysis progress check."""

import json
import runpy
import sys
from pathlib import Path


def main():
    request = runpy.run_path(str(Path(__file__).with_name("verify-phase14.py")))["request"]
    info = request("system/speech-precision")
    if info.get("version") != "speech_precision_v1" or not info.get("read_only") or info.get("hosted_model_calls") != 0:
        raise RuntimeError("the speech precision build is not ready")
    print(json.dumps(info, indent=2))
    print("PASS  Local speech precision is installed; background progress is shown above.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Speech precision verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
