#!/usr/bin/env python3
"""Verify reusable creative profiles and zero-model-call delivery variants."""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def configured_base_url() -> str:
    explicit = os.environ.get("GM_MEDIA_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    values: dict[str, str] = {}
    environment_file = Path(__file__).resolve().parents[1] / ".env"
    if environment_file.is_file():
        for raw_line in environment_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    if values.get("TAILSCALE_AUTH_REQUIRED", "").lower() == "true" and values.get("APP_ORIGIN"):
        return f"{values['APP_ORIGIN'].rstrip('/')}/api/media"
    return "http://127.0.0.1:3000/api/media"


BASE_URL = configured_base_url()


def request(path: str, *, method: str = "GET", payload: dict | None = None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    http_request = urllib.request.Request(
        f"{BASE_URL}/{path.lstrip('/')}",
        data=body,
        headers={"content-type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(http_request, timeout=3600) as response:
            raw = response.read()
            if not raw:
                decoded = None
            elif "json" in response.headers.get("content-type", ""):
                decoded = json.loads(raw)
            else:
                decoded = raw
            return response.status, decoded
    except urllib.error.HTTPError as error:
        try:
            decoded = json.loads(error.read())
        except Exception:
            decoded = {"detail": f"HTTP {error.code}"}
        return error.code, decoded


def require(path: str, expected: int, *, method: str = "GET", payload: dict | None = None):
    status, response = request(path, method=method, payload=payload)
    if status != expected:
        raise RuntimeError(f"{method} {path} returned {status}: {response}")
    return response


def main() -> int:
    usage = require("usage?days=0", 200)
    candidates = [
        job for job in usage.get("job_history", [])
        if job.get("history_kind") == "editing" and job.get("status") == "delivered"
    ]
    selected_review = None
    for candidate in candidates:
        review = require(f"jobs/{candidate['id']}/review", 200)
        if (review.get("final_export") or {}).get("status") == "ready":
            selected_review = review
            break
    if selected_review is None:
        raise RuntimeError("approve one final delivery before running Phase 10 verification")

    job_id = selected_review["job"]["id"]
    usage_before = int(selected_review.get("usage", {}).get("total_tokens", 0))
    profile_name = "Phase 10 verification " + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    profile = require(
        f"jobs/{job_id}/creative-profile",
        201,
        method="POST",
        payload={"name": profile_name, "description": "Temporary automated verification profile"},
    )
    try:
        profiles = require("creative-profiles", 200)
        if not any(item.get("id") == profile.get("id") for item in profiles):
            raise RuntimeError("saved creative profile was not returned by the catalogue")

        variant = require(
            f"jobs/{job_id}/variants",
            202,
            method="POST",
            payload={"output_aspect": "square", "target_duration_seconds": 15},
        )
        deadline = time.monotonic() + 1800
        while variant.get("status") not in {"ready", "failed"}:
            if time.monotonic() >= deadline:
                raise RuntimeError("delivery variant did not finish within 30 minutes")
            time.sleep(3)
            review = require(f"jobs/{job_id}/review", 200)
            variant = next(
                item for item in review.get("delivery_variants", []) if item.get("id") == variant["id"]
            )
        if variant.get("status") != "ready" or not variant.get("files_available"):
            raise RuntimeError(f"delivery variant failed: {variant.get('error')}")
        manifest = require(
            f"jobs/{job_id}/variants/{variant['id']}/manifest",
            200,
        )
        render = manifest.get("render", {})
        provenance = manifest.get("delivery_variant", {})
        if render.get("width") != 1080 or render.get("height") != 1080:
            raise RuntimeError("square variant did not render at 1080 by 1080")
        if provenance.get("derived_without_model_call") is not True:
            raise RuntimeError("variant manifest does not declare zero-model derivation")
        package = require(f"jobs/{job_id}/variants/{variant['id']}/package", 200)
        if not isinstance(package, bytes) or not package.startswith(b"PK"):
            raise RuntimeError("variant package is not a downloadable ZIP archive")
        refreshed = require(f"jobs/{job_id}/review", 200)
        usage_after = int(refreshed.get("usage", {}).get("total_tokens", 0))
        if usage_after != usage_before:
            raise RuntimeError("creating a delivery variant unexpectedly changed model token usage")
        print(
            json.dumps(
                {
                    "status": "passed",
                    "job_id": job_id,
                    "profile_round_trip": True,
                    "variant_id": variant["id"],
                    "variant_aspect": "square",
                    "variant_target_seconds": 15,
                    "additional_model_tokens": 0,
                    "phone_download_verified": True,
                },
                indent=2,
            )
        )
    finally:
        require(f"creative-profiles/{profile['id']}", 204, method="DELETE")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Phase 10 verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
