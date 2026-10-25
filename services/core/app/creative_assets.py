import hashlib
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from psycopg.errors import UniqueViolation

from app.config import get_settings
from app.database import connection
from app.media_analysis import READ_ONLY_MODE, ensure_capacity, probe_media, resolve_source
from app.productization import actor_login, require_owner
from app.schemas import CreativeAssetResponse, MusicTrackResponse


router = APIRouter(prefix="/api/v1", tags=["creative-assets"])
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
PLATFORMS = {"all_social", "facebook", "instagram", "linkedin", "tiktok", "youtube"}
AUDIO_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"}
IMAGE_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".png", ".webp"}


def _csv(value: str, *, allowed: set[str] | None = None) -> list[str]:
    items = list(dict.fromkeys(part.strip().lower() for part in value.split(",") if part.strip()))
    if allowed is not None and any(item not in allowed for item in items):
        raise HTTPException(status_code=422, detail="one or more values are unsupported")
    return items


def _https_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise HTTPException(status_code=422, detail="license source URL must be a public https URL")
    return value.strip()


def _safe_filename(value: str) -> str:
    name = Path(value).name.strip()
    safe = SAFE_NAME.sub("-", name).strip(".-")
    if not safe or len(safe) > 180:
        raise HTTPException(status_code=422, detail="source filename is invalid")
    return safe


def _validate_probe(kind: str, suffix: str, probe: dict[str, Any]) -> float | None:
    streams = {str(stream.get("type")) for stream in probe.get("streams", [])}
    if kind in {"music", "sound_effect", "meme_sound"}:
        if suffix not in AUDIO_EXTENSIONS or "audio" not in streams:
            raise HTTPException(status_code=422, detail="this creative asset must be a supported audio file")
    elif suffix not in IMAGE_EXTENSIONS or "video" not in streams:
        raise HTTPException(status_code=422, detail="this creative asset must be a PNG, JPEG, WebP, or GIF")
    duration = probe.get("format", {}).get("duration_seconds")
    return float(duration) if isinstance(duration, (int, float)) and duration > 0 else None


@router.get("/creative-assets", response_model=list[CreativeAssetResponse])
def list_creative_assets(active: bool | None = Query(default=True)) -> list[dict[str, Any]]:
    clauses = ["commercial_use = true", "synthetic_media = false"]
    parameters: list[Any] = []
    if active is not None:
        clauses.append("active = %s")
        parameters.append(active)
    with connection() as database:
        rows = database.execute(
            f"""SELECT id, kind, title, creator, source_name, mime_type, byte_size,
                       duration_seconds, tags, purpose, license_name, license_source_url,
                       allowed_platforms, attribution, synthetic_media, active,
                       created_at, updated_at
                FROM creative_assets
                WHERE {' AND '.join(clauses)}
                ORDER BY kind, purpose, title""",
            tuple(parameters),
        ).fetchall()
    return list(rows)


@router.get("/creative-assets/{asset_id}/media")
def creative_asset_media(asset_id: UUID) -> FileResponse:
    with connection() as database:
        row = database.execute(
            "SELECT storage_key, source_name, mime_type FROM creative_assets WHERE id = %s",
            (asset_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="creative asset not found")
    source = resolve_source(get_settings().media_root, str(row["storage_key"]))
    if not source.is_file():
        raise HTTPException(status_code=404, detail="creative asset file is unavailable")
    return FileResponse(source, media_type=row["mime_type"], filename=row["source_name"])


@router.get("/music-tracks/{track_id}/media")
def music_track_media(track_id: UUID) -> FileResponse:
    with connection() as database:
        row = database.execute(
            "SELECT storage_key, title FROM music_tracks WHERE id=%s", (track_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="music track not found")
    source = resolve_source(get_settings().media_root, str(row["storage_key"]))
    if not source.is_file():
        raise HTTPException(status_code=404, detail="music track file is unavailable")
    return FileResponse(source, filename=source.name, media_type=mimetypes.guess_type(source.name)[0])


@router.patch("/music-tracks/{track_id}", response_model=MusicTrackResponse)
def set_music_track_state(
    track_id: UUID,
    active: bool = Query(...),
    x_gm_user_login: str | None = Header(default=None),
) -> dict[str, Any]:
    require_owner(actor_login(x_gm_user_login))
    with connection() as database:
        row = database.execute(
            """UPDATE music_tracks SET active=%s, updated_at=now() WHERE id=%s
               RETURNING id, title, artist, duration_seconds, mood, energy, bpm,
                         beat_grid_seconds, license_name, license_source_url,
                         allowed_platforms, attribution, active, created_at""",
            (active, track_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="music track not found")
    return row


@router.patch("/creative-assets/{asset_id}", response_model=CreativeAssetResponse)
def set_creative_asset_state(
    asset_id: UUID,
    active: bool = Query(...),
    x_gm_user_login: str | None = Header(default=None),
) -> dict[str, Any]:
    require_owner(actor_login(x_gm_user_login))
    with connection() as database:
        row = database.execute(
            "UPDATE creative_assets SET active=%s, updated_at=now() WHERE id=%s RETURNING *",
            (active, asset_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="creative asset not found")
    return row


@router.post("/creative-assets/import", status_code=status.HTTP_201_CREATED)
async def import_creative_asset(
    request: Request,
    kind: Literal["music", "sound_effect", "meme_sound", "sticker", "gif", "meme_image"] = Query(...),
    filename: str = Query(...),
    title: str = Query(..., min_length=1, max_length=200),
    creator: str = Query(default="", max_length=200),
    tags: str = Query(default="", max_length=600),
    purpose: Literal["hook", "transition", "emphasis", "reveal", "reaction", "payoff"] = Query(default="emphasis"),
    mood: str = Query(default="uplifting", min_length=1, max_length=80),
    energy: Literal["low", "medium", "high"] = Query(default="medium"),
    license_name: str = Query(..., min_length=1, max_length=200),
    license_source_url: str = Query(..., min_length=8, max_length=1000),
    license_proof: str = Query(default="", max_length=2000),
    attribution: str = Query(default="", max_length=1000),
    allowed_platforms: str = Query(default="all_social", max_length=200),
    commercial_use_confirmed: bool = Query(default=False),
    x_gm_user_login: str | None = Header(default=None),
) -> dict[str, Any]:
    require_owner(actor_login(x_gm_user_login))
    if not commercial_use_confirmed:
        raise HTTPException(status_code=422, detail="commercial-use rights must be confirmed before import")
    ensure_capacity(get_settings())
    clean_filename = _safe_filename(filename)
    source_url = _https_url(license_source_url)
    platforms = _csv(allowed_platforms, allowed=PLATFORMS)
    if not platforms:
        raise HTTPException(status_code=422, detail="choose at least one allowed platform")
    tag_values = _csv(tags)[:20]
    body = await request.body()
    if not body or len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="creative asset must be between 1 byte and 200 MB")

    settings = get_settings()
    asset_id = uuid4()
    suffix = Path(clean_filename).suffix.lower()
    category = "music" if kind == "music" else "effects"
    relative = Path("creative") / category / str(asset_id) / clean_filename
    destination = settings.media_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.part")
    try:
        temporary.write_bytes(body)
        probe = probe_media(temporary, settings.analysis_command_timeout_seconds)
        duration = _validate_probe(kind, suffix, probe)
        sha256 = hashlib.sha256(body).hexdigest()
        mime_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if not mime_type.startswith(("audio/", "image/")):
            mime_type = mimetypes.guess_type(clean_filename)[0] or "application/octet-stream"
        temporary.chmod(READ_ONLY_MODE)
        os.replace(temporary, destination)
        destination.chmod(READ_ONLY_MODE)
        try:
            with connection() as database:
                if kind == "music":
                    row = database.execute(
                        """INSERT INTO music_tracks (
                               id, title, artist, storage_key, sha256, duration_seconds,
                               mood, energy, license_name, license_source_url, license_proof,
                               commercial_use, synthetic_media, allowed_platforms, attribution
                           ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,false,%s::jsonb,%s)
                           RETURNING id, title, artist, duration_seconds, mood, energy, bpm,
                                     beat_grid_seconds, license_name, license_source_url,
                                     allowed_platforms, attribution, active, created_at""",
                        (asset_id, title.strip(), creator.strip(), relative.as_posix(), sha256,
                         duration or 0.001, mood.strip(), energy, license_name.strip(), source_url,
                         license_proof.strip(), json.dumps(platforms), attribution.strip()),
                    ).fetchone()
                else:
                    row = database.execute(
                        """INSERT INTO creative_assets (
                               id, kind, title, creator, source_name, storage_key, sha256,
                               mime_type, byte_size, duration_seconds, tags, purpose,
                               license_name, license_source_url, license_proof, commercial_use,
                               synthetic_media, allowed_platforms, attribution
                           ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,true,false,%s::jsonb,%s)
                           RETURNING *""",
                        (asset_id, kind, title.strip(), creator.strip(), clean_filename,
                         relative.as_posix(), sha256, mime_type, len(body), duration,
                         json.dumps(tag_values), purpose, license_name.strip(), source_url,
                         license_proof.strip(), json.dumps(platforms), attribution.strip()),
                    ).fetchone()
        except UniqueViolation as error:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=409, detail="this exact creative file is already in the library") from error
    except HTTPException:
        temporary.unlink(missing_ok=True)
        raise
    except Exception:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise
    assert row is not None
    return {"kind": kind, "asset": dict(row)}
