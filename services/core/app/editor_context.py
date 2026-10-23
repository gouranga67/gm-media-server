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
            contact_sheet = manifest.get("derived", {}).get("contact_sheet")
            if isinstance(contact_sheet, str):
                asset["_contact_sheet_key"] = contact_sheet
        assets.append(asset)

    ready = bool(assets) and all(
        asset["asset_status"] == "ready" and asset["analysis_status"] == "ready"
        for asset in assets
    )
    return {
        "job": {
            "id": str(job["id"]),
            "project_id": str(job["project_id"]),
            "recipe": job["recipe"],
            "status": job["status"],
            "revision": job["revision"],
        },
        "project": {
            "name": job["project_name"],
            "brief": job["brief"],
            "privacy_mode": job["privacy_mode"],
            "ai_copy_allowed": job["ai_copy_allowed"],
        },
        "ready_for_editing": ready,
        "assets": assets,
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
