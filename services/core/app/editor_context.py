import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

from app.config import Settings, get_settings
from app.broll_evidence import broll_guidance
from app.database import connection
from app.edit_plan import source_word_gaps
from app.media_analysis import probe_media, resolve_source, video_probe_is_hdr
from app.learning import learning_context_for_job
from app.take_quality import editing_policy, take_quality_report
from app.story_intelligence import (
    STORY_INTELLIGENCE_VERSION,
    build_story_assessment,
    select_story_moments,
)
from app.source_evidence import shared_evidence


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
                   asset_library_metadata.display_name, asset_library_metadata.media_role,
                   asset_library_metadata.media_category, asset_library_metadata.tags, asset_library_metadata.notes,
                   asset_ingests.status AS analysis_status, asset_ingests.manifest,
                   asset_story_indexes.status AS story_status,
                   asset_story_indexes.story_version,
                   asset_story_indexes.moments AS story_moments
            FROM job_assets
            JOIN assets ON assets.id = job_assets.asset_id
            LEFT JOIN asset_library_metadata ON asset_library_metadata.asset_id = assets.id
            LEFT JOIN asset_ingests ON asset_ingests.asset_id = assets.id
            LEFT JOIN asset_story_indexes ON asset_story_indexes.asset_id = assets.id
            WHERE job_assets.job_id = %s
            ORDER BY job_assets.created_at, assets.created_at
            """,
            (job_id,),
        ).fetchall()
        concept_selection = database.execute("""
            SELECT r.id AS request_id,c.concept_id,r.concepts FROM reel_concept_jobs c
            JOIN reel_concept_requests r ON r.id=c.request_id WHERE c.job_id=%s
        """, (job_id,)).fetchone()
        music_rows = database.execute(
            """
            SELECT * FROM music_tracks
            WHERE active = true AND commercial_use = true
            ORDER BY (id = %s) DESC, mood, energy, title
            """,
            (job.get("selected_music_track_id"),),
        ).fetchall()
        creative_rows = database.execute(
            """SELECT * FROM creative_assets
               WHERE active=true AND commercial_use=true AND synthetic_media=false
               ORDER BY purpose, kind, title"""
        ).fetchall()
        brand_kit = None
        if job.get("brand_kit_id") is not None:
            brand_kit = database.execute(
                "SELECT * FROM brand_kits WHERE id = %s", (job["brand_kit_id"],)
            ).fetchone()
        learning_preferences = learning_context_for_job(database, job)
        products = list(database.execute("SELECT id,name,aliases FROM source_products ORDER BY name LIMIT 100").fetchall())
        annotations = list(database.execute(
            "SELECT id,asset_id,start_seconds,end_seconds,role,note FROM asset_range_annotations "
            "WHERE asset_id=ANY(%s) ORDER BY start_seconds LIMIT 500", ([row["id"] for row in rows],)).fetchall())

    story_query = " ".join(
        str(value or "")
        for value in (
            job["brief"], job.get("must_include"), job.get("audience"),
            job.get("story_goal"), job.get("desired_feeling"),
            job.get("ending_instruction"),
        )
    )
    assets: list[dict[str, Any]] = []
    retrieved_story_moments: list[dict[str, Any]] = []
    for row in rows:
        manifest = row.get("manifest") if isinstance(row.get("manifest"), dict) else {}
        streams = _stream_types(manifest)
        probe_format = manifest.get("probe", {}).get("format", {})
        transcript = _read_transcript(settings, manifest) if row.get("analysis_status") == "ready" else []
        story_moments = select_story_moments(
            row.get("story_moments") if isinstance(row.get("story_moments"), list) else [],
            story_query,
        )
        for moment in story_moments:
            moment["asset_id"] = str(row["id"])
            moment["source_name"] = row["source_name"]
        retrieved_story_moments.extend(story_moments)
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
            "take_quality": take_quality_report(transcript),
            "story_index": {
                "status": row.get("story_status") or "pending",
                "version": row.get("story_version") or STORY_INTELLIGENCE_VERSION,
                "moments": story_moments,
            },
        }
        if row.get("display_name"):
            asset["library_name"] = row["display_name"]
        if row.get("media_role") in ("talking", "broll"):
            asset["library_role"] = row["media_role"]
        asset["source_evidence"] = shared_evidence(asset, row, manifest, transcript, products,
            [annotation for annotation in annotations if str(annotation["asset_id"]) == str(row["id"])])
        gaps = source_word_gaps(asset, 0, float(asset.get("duration_seconds") or 0))
        longest = sorted((gap for gap in gaps if gap[2] >= 0.65),
                         key=lambda gap: gap[2], reverse=True)[:24]
        asset["speech_gaps"] = [
            {"start": round(start, 3), "end": round(end, 3), "duration_seconds": round(length, 3)}
            for start, end, length in sorted(longest)
        ]
        asset["speech_gap_note"] = (
            "Word-timing gaps, not verified silence; may contain laughter, actions, or reactions."
        )
        if job.get("edit_style") == "high_impact":
            asset["broll_guidance"] = broll_guidance(asset)
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
    story_assessment = build_story_assessment(retrieved_story_moments)
    creative_library: list[dict[str, Any]] = []
    for row in creative_rows:
        allowed_platforms = row.get("allowed_platforms") or []
        if "all_social" not in allowed_platforms and target_platform not in allowed_platforms:
            continue
        item = {
            "asset_id": str(row["id"]), "kind": row["kind"], "title": row["title"],
            "creator": row["creator"], "duration_seconds": row["duration_seconds"],
            "tags": row["tags"], "purpose": row["purpose"],
            "allowed_platforms": allowed_platforms, "attribution": row["attribution"],
            "license_name": row["license_name"], "license_source_url": row["license_source_url"],
        }
        if include_internal_paths:
            item["_storage_key"] = row["storage_key"]
        creative_library.append(item)
    context = {
        "job": {
            "id": str(job["id"]),
            "project_id": str(job["project_id"]),
            "recipe": job["recipe"],
            "status": job["status"],
            "revision": job["revision"],
            "target_duration_seconds": job["target_duration_seconds"],
            "edit_style": job["edit_style"],
            "music_mode": job["music_mode"],
            "selected_music_track_id": (
                str(job["selected_music_track_id"]) if job.get("selected_music_track_id") else None
            ),
            "effect_level": job.get("effect_level") or "off",
            "target_platform": job["target_platform"],
            "must_include": job["must_include"],
            "audience": job.get("audience") or "",
            "story_goal": job.get("story_goal") or "",
            "desired_feeling": job.get("desired_feeling") or "",
            "ending_instruction": job.get("ending_instruction") or "",
            "editor_model": job.get("editor_model"),
            "reasoning_effort": job.get("reasoning_effort") or "medium",
            "output_aspect": job.get("output_aspect") or "vertical",
            "brand_kit_id": str(job["brand_kit_id"]) if job.get("brand_kit_id") else None,
            "publishing_preset": job.get("publishing_preset") or "custom",
            "cover_time_seconds": float(job.get("cover_time_seconds") or 0),
            "editorial_policy": editing_policy(job),
        },
        "project": {
            "name": job["project_name"],
            "brief": job["brief"],
            "privacy_mode": job["privacy_mode"],
            "ai_copy_allowed": job["ai_copy_allowed"],
        },
        "story_spine": {
            "audience": job.get("audience") or "",
            "goal": job.get("story_goal") or job["brief"],
            "desired_feeling": job.get("desired_feeling") or "",
            "must_include": job["must_include"],
            "ending": job.get("ending_instruction") or "",
            "recommended_shape": (
                ["tease", "establish", "build", "best_moment", "reaction", "finish"]
                if job["recipe"] == "montage"
                else ["hook", "context", "development", "payoff", "ending"]
            ),
            "engagement_assessment": story_assessment,
        },
        "ready_for_editing": ready,
        "assets": assets,
        "music_library": music_library,
        "creative_effect_library": creative_library,
        "brand_kit": (
            {
                "id": str(brand_kit["id"]),
                "name": brand_kit["name"],
                "primary_color": brand_kit["primary_color"],
                "accent_color": brand_kit["accent_color"],
                "caption_style": brand_kit["caption_style"],
                "font_family": brand_kit["font_family"],
            }
            if brand_kit is not None else None
        ),
        "learning_preferences": learning_preferences,
        "content_policy": {
            "source_derived_only": not music_library and not creative_library,
            "approved_library_music": bool(music_library),
            "approved_library_effects": bool(creative_library),
            "synthetic_image": False,
            "synthetic_video": False,
            "synthetic_voice": False,
            "synthetic_music": False,
        },
    }

    if concept_selection:
        selected = next((item for item in concept_selection["concepts"] if item["id"] == str(concept_selection["concept_id"])), None)
        if selected:
            context["selected_concept"] = {"request_id": str(concept_selection["request_id"]),
                "title": selected["title"], "script": selected["script"], "visuals": selected["visuals"],
                "reel_kind": selected.get("reel_kind", "story")}
    return context


def resolve_internal_asset_source(settings: Settings, asset: dict[str, Any]) -> Path:
    storage_key = asset.get("_storage_key")
    if not isinstance(storage_key, str):
        raise ValueError("editor context does not contain an internal storage key")
    return resolve_source(settings.media_root, storage_key)


@lru_cache(maxsize=1024)
def _source_is_hdr(source: str, timeout: int) -> bool:
    return video_probe_is_hdr(probe_media(Path(source), timeout))


def resolve_internal_asset_render_source(settings: Settings, asset: dict[str, Any]) -> Path:
    """Prefer the ingest-normalized video proxy for deterministic rendering."""

    original = resolve_internal_asset_source(settings, asset)
    try:
        if _source_is_hdr(str(original), settings.analysis_command_timeout_seconds):
            # Older proxies were created before tone mapping was available.
            # Render HDR originals directly so existing library assets recover
            # without destructive re-ingest or replacement.
            return original
    except (OSError, RuntimeError, ValueError):
        pass
    proxy_key = asset.get("_proxy_key")
    if isinstance(proxy_key, str):
        return resolve_source(settings.media_root, proxy_key)
    return original
