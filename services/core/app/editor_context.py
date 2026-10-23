import json
from pathlib import Path
from typing import Any
from uuid import UUID

from app.config import Settings, get_settings
from app.database import connection
from app.media_analysis import resolve_source


def _stream_types(manifest: dict[str, Any]) -> set[str]:
    return {
        str(stream.get("type"))
        for stream in manifest.get("probe", {}).get("streams", [])
        if isinstance(stream, dict)
    }


def _read_transcript(settings: Settings, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    transcript_key = manifest.get("derived", {}).get("transcript")
    if not isinstance(transcript_key, str):
        return []
    transcript_path = resolve_source(settings.media_root, transcript_key)
    payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    segments = payload.get("segments", [])
    return segments if isinstance(segments, list) else []


def build_editor_context(
    job_id: UUID | str,
    *,
    include_internal_paths: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    with connection() as database:
        job = database.execute(
            """
            SELECT jobs.*, projects.name AS project_name, projects.brief,
                   projects.privacy_mode, projects.ai_copy_allowed
            FROM jobs
            JOIN projects ON projects.id = jobs.project_id
            WHERE jobs.id = %s
            """,
            (job_id,),
        ).fetchone()
        if job is None:
            raise LookupError("job not found")
        rows = database.execute(
            """
            SELECT assets.id, assets.source_name, assets.mime_type, assets.byte_size,
                   assets.sha256, assets.storage_key, assets.status AS asset_status,
                   asset_ingests.status AS analysis_status, asset_ingests.manifest
            FROM job_assets
            JOIN assets ON assets.id = job_assets.asset_id
            LEFT JOIN asset_ingests ON asset_ingests.asset_id = assets.id
            WHERE job_assets.job_id = %s
            ORDER BY job_assets.created_at, assets.created_at
            """,
            (job_id,),
        ).fetchall()
        music_rows = database.execute(
            """
            SELECT * FROM music_tracks
            WHERE active = true AND commercial_use = true
            ORDER BY mood, energy, title
            """
        ).fetchall()

    assets: list[dict[str, Any]] = []
    for row in rows:
        manifest = row.get("manifest") if isinstance(row.get("manifest"), dict) else {}
        streams = _stream_types(manifest)
        probe_format = manifest.get("probe", {}).get("format", {})
        transcript = _read_transcript(settings, manifest) if row.get("analysis_status") == "ready" else []
        asset: dict[str, Any] = {
            "asset_id": str(row["id"]),
            "source_name": row["source_name"],
            "mime_type": row["mime_type"],
            "byte_size": row["byte_size"],
            "sha256": row["sha256"],
            "asset_status": row["asset_status"],
            "analysis_status": row["analysis_status"] or "not_queued",
            "duration_seconds": probe_format.get("duration_seconds"),
            "has_video": "video" in streams,
            "has_audio": "audio" in streams,
            "scene_boundaries_seconds": manifest.get("derived", {}).get(
                "scene_boundaries_seconds", []
            ),
            "visual_quality": manifest.get("derived", {}).get("visual_quality", {}),
            "loudness": manifest.get("derived", {}).get("loudness", {}),
            "transcript_segments": transcript,
        }
        if include_internal_paths:
            asset["_storage_key"] = row["storage_key"]
            proxy = manifest.get("derived", {}).get("proxy")
            if asset["has_video"] and isinstance(proxy, str):
                asset["_proxy_key"] = proxy
            contact_sheet = manifest.get("derived", {}).get("contact_sheet")
            if isinstance(contact_sheet, str):
                asset["_contact_sheet_key"] = contact_sheet
            preview = manifest.get("derived", {}).get("preview") or manifest.get(
                "derived", {}
            ).get("thumbnail")
            if isinstance(preview, str):
                asset["_preview_key"] = preview
        assets.append(asset)

    ready = bool(assets) and all(
        asset["asset_status"] == "ready" and asset["analysis_status"] == "ready"
        for asset in assets
    )
    music_library: list[dict[str, Any]] = []
    target_platform = job["target_platform"]
    for row in music_rows:
        allowed_platforms = row["allowed_platforms"]
        if target_platform is None or not isinstance(allowed_platforms, list):
            continue
        if "all_social" not in allowed_platforms and target_platform not in allowed_platforms:
            continue
        track = {
            "track_id": str(row["id"]),
            "title": row["title"],
            "artist": row["artist"],
            "duration_seconds": row["duration_seconds"],
            "mood": row["mood"],
            "energy": row["energy"],
            "bpm": float(row["bpm"]) if row["bpm"] is not None else None,
            "beat_grid_seconds": row.get("beat_grid_seconds") or [],
            "license_name": row["license_name"],
            "license_source_url": row["license_source_url"],
            "license_proof_recorded": bool(row["license_proof"]),
            "allowed_platforms": row["allowed_platforms"],
            "attribution": row["attribution"],
        }
        if include_internal_paths:
            track["_storage_key"] = row["storage_key"]
        music_library.append(track)
    return {
        "job": {
            "id": str(job["id"]),
            "project_id": str(job["project_id"]),
            "recipe": job["recipe"],
            "status": job["status"],
            "revision": job["revision"],
            "target_duration_seconds": job["target_duration_seconds"],
            "edit_style": job["edit_style"],
            "music_mode": job["music_mode"],
            "target_platform": job["target_platform"],
            "must_include": job["must_include"],
            "editor_model": job.get("editor_model"),
            "reasoning_effort": job.get("reasoning_effort") or "medium",
            "output_aspect": job.get("output_aspect") or "vertical",
        },
        "project": {
            "name": job["project_name"],
            "brief": job["brief"],
            "privacy_mode": job["privacy_mode"],
            "ai_copy_allowed": job["ai_copy_allowed"],
        },
        "ready_for_editing": ready,
        "assets": assets,
        "music_library": music_library,
        "content_policy": {
            "source_derived_only": True,
            "synthetic_image": False,
            "synthetic_video": False,
            "synthetic_voice": False,
            "synthetic_music": False,
        },
    }


def resolve_internal_asset_source(settings: Settings, asset: dict[str, Any]) -> Path:
    storage_key = asset.get("_storage_key")
    if not isinstance(storage_key, str):
        raise ValueError("editor context does not contain an internal storage key")
    return resolve_source(settings.media_root, storage_key)


def resolve_internal_asset_render_source(settings: Settings, asset: dict[str, Any]) -> Path:
    """Prefer the ingest-normalized video proxy for deterministic rendering."""

    proxy_key = asset.get("_proxy_key")
    if isinstance(proxy_key, str):
        return resolve_source(settings.media_root, proxy_key)
    return resolve_internal_asset_source(settings, asset)
