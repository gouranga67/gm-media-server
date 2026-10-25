#!/usr/bin/env python3
"""Verify the deployed Phase 16 creative library without rendering or model usage."""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


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


def inspect_libraries(music, effects, context):
    """Verify catalogue evidence and the platform-filtered view supplied to the editor."""
    for item in [*music, *effects]:
        source = urlparse(item.get("license_source_url") or "")
        if not item.get("license_name") or source.scheme != "https" or not source.netloc:
            raise RuntimeError("a creative library asset is missing its license metadata")
        platforms = item.get("allowed_platforms")
        if not isinstance(platforms, list) or not platforms:
            raise RuntimeError("a creative library asset has no allowed platforms")
    platform = context["job"].get("target_platform")
    library = context.get("creative_effect_library")
    if not isinstance(library, list):
        raise RuntimeError("editor context does not contain the licensed creative effect library")
    expected = {str(item["id"]): item for item in effects
                if "all_social" in item["allowed_platforms"] or platform in item["allowed_platforms"]}
    if {str(item.get("asset_id")) for item in library} != set(expected):
        raise RuntimeError("editor effect inventory differs from its platform-compatible catalogue")
    for item in library:
        catalogue = expected[str(item["asset_id"])]
        for field in ("kind", "purpose", "license_name", "license_source_url", "allowed_platforms"):
            if item.get(field) != catalogue.get(field):
                raise RuntimeError(f"editor effect metadata differs from the catalogue: {field}")
    kinds = {item["kind"] for item in library}
    compatible_music = [item for item in music if "all_social" in item["allowed_platforms"]
                        or platform in item["allowed_platforms"]]
    return {
        "compatible_music_tracks": len(compatible_music),
        "compatible_creative_effects": len(library),
        "sound_effects_ready": bool(kinds & {"sound_effect", "meme_sound"}),
        "visual_effects_ready": bool(kinds & {"sticker", "gif", "meme_image"}),
        "creative_effects_ready": bool(kinds & {"sound_effect", "meme_sound"})
                                  and bool(kinds & {"sticker", "gif", "meme_image"}),
        "platform_filtering": True,
        "rights_metadata": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-effects-ready", action="store_true",
                        help="also require compatible sounds and visual effects to have been imported")
    arguments = parser.parse_args()
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
    readiness = inspect_libraries(music, effects, context)
    if arguments.require_effects_ready and not readiness["creative_effects_ready"]:
        raise RuntimeError("creative effects are not ready: import compatible sounds and stickers with "
                           "python3 scripts/import-creative-starter-library.py, then rerun this check")
    notices = []
    if not readiness["creative_effects_ready"]:
        notices.append("The effects library is incomplete. A passing catalogue check does not mean FX are ready.")
    if job.get("effect_level") == "off":
        notices.append("Creative effects are Off for the latest job. Choose Social for your next FX test.")
    print(json.dumps({"status": "passed", "job_id": job.get("id"),
        "music_tracks": len(music), "creative_effects": len(effects),
        "effect_level": job.get("effect_level"), **readiness,
        "verification_scope": "catalogue_and_editor_context",
        "notices": notices, "additional_model_tokens": 0}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Phase 16 verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
