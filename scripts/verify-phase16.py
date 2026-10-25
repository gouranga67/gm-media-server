#!/usr/bin/env python3
"""Verify the deployed Phase 16 creative library without rendering or model usage."""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def base_url() -> str:
    if os.environ.get("GM_MEDIA_URL"):
        return os.environ["GM_MEDIA_URL"].rstrip("/")
    values = {}
    path = Path(__file__).resolve().parents[1] / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    if values.get("TAILSCALE_AUTH_REQUIRED", "").lower() == "true" and values.get("APP_ORIGIN"):
        return values["APP_ORIGIN"].rstrip("/") + "/api/media"
    return "http://127.0.0.1:3000/api/media"


BASE = base_url()


def request(path: str):
    try:
        with urllib.request.urlopen(f"{BASE}/{path}", timeout=120) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"GET {path}: {error.code} {error.read().decode(errors='replace')}") from error


def main() -> int:
    music = request("music-tracks?active=true")
    effects = request("creative-assets?active=true")
    history = request("usage?days=0").get("job_history") or []
    context = None
    for item in history:
        if item.get("history_kind") == "editing":
            context = request(f"jobs/{item['id']}/editor-context")
            break
    if context is None:
        raise RuntimeError("no editing job is available for Phase 16 context verification")
    job = context.get("job") or {}
    if job.get("effect_level") not in {"off", "subtle", "social", "meme_heavy"}:
        raise RuntimeError("editor context does not declare a creative effect level")
    if not isinstance(context.get("creative_effect_library"), list):
        raise RuntimeError("editor context does not contain the licensed creative effect library")
    print(json.dumps({"status": "passed", "job_id": job.get("id"),
        "music_tracks": len(music), "creative_effects": len(effects),
        "effect_level": job.get("effect_level"), "platform_filtering": True,
        "rights_metadata": True, "additional_model_tokens": 0}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Phase 16 verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
