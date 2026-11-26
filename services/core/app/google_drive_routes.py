"""Owner-only Google Drive connection and explicit library import routes."""

import hashlib
import json
import secrets
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator
from redis import Redis

from app.config import get_settings
from app.database import connection
from app import google_drive as drive


router = APIRouter(prefix="/api/v1/google-drive", tags=["google-drive"])


def _owner(role: str | None, login: str | None) -> str:
    settings = get_settings()
    if settings.tailscale_auth_required and role != "owner":
        raise HTTPException(status_code=403, detail="owner access is required")
    if role and role != "owner":
        raise HTTPException(status_code=403, detail="owner access is required")
    return (login or settings.tailscale_owner_login or "local-owner").strip().lower()


def _require_configuration() -> Any:
    settings = get_settings()
    if not drive.configured(settings):
        raise HTTPException(status_code=503, detail="Google Drive import has not been configured on this server")
    return settings


def _connection_for(actor: str) -> dict[str, Any]:
    with connection() as database:
        row = database.execute(
            "SELECT * FROM google_drive_connections WHERE actor_login = %s", (actor,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=409, detail="connect Google Drive before choosing files")
    return row


@router.get("/status")
def status(
    x_gm_user_role: str | None = Header(default=None),
    x_gm_user_login: str | None = Header(default=None),
) -> dict[str, Any]:
    actor = _owner(x_gm_user_role, x_gm_user_login)
    settings = get_settings()
    if not drive.configured(settings):
        return {"enabled": False, "connected": False}
    with connection() as database:
        row = database.execute(
            "SELECT connected_at, updated_at FROM google_drive_connections WHERE actor_login = %s",
            (actor,),
        ).fetchone()
    return {"enabled": True, "connected": row is not None, **(row or {})}


@router.get("/connect")
def connect(
    x_gm_user_role: str | None = Header(default=None),
    x_gm_user_login: str | None = Header(default=None),
) -> RedirectResponse:
    actor = _owner(x_gm_user_role, x_gm_user_login)
    settings = _require_configuration()
    raw_state = secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw_state.encode()).hexdigest()
    with connection() as database:
        database.execute("DELETE FROM google_drive_oauth_states WHERE expires_at < now()")
        database.execute(
            """INSERT INTO google_drive_oauth_states (state_digest, actor_login, expires_at)
               VALUES (%s, %s, now() + interval '10 minutes')""",
            (digest, actor),
        )
    return RedirectResponse(drive.authorization_url(settings, raw_state), status_code=303)


@router.get("/callback")
def callback(
    state: str = Query(min_length=20, max_length=200),
    code: str | None = Query(default=None, min_length=1, max_length=4096),
    error: str | None = Query(default=None, max_length=200),
    x_gm_user_role: str | None = Header(default=None),
    x_gm_user_login: str | None = Header(default=None),
) -> RedirectResponse:
    actor = _owner(x_gm_user_role, x_gm_user_login)
    settings = _require_configuration()
    digest = hashlib.sha256(state.encode()).hexdigest()
    with connection() as database:
        saved = database.execute(
            """DELETE FROM google_drive_oauth_states
               WHERE state_digest = %s AND actor_login = %s AND expires_at >= now()
               RETURNING actor_login""",
            (digest, actor),
        ).fetchone()
    if saved is None:
        raise HTTPException(status_code=409, detail="Google Drive connection expired; start again")
    if error or not code:
        return RedirectResponse(settings.google_drive_app_origin + "/library?drive=cancelled", status_code=303)
    try:
        tokens = drive.exchange_code(settings, code)
    except drive.GoogleDriveError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    refresh_token = tokens.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise HTTPException(status_code=409, detail="Google did not return offline access; remove GM Studio from Google permissions and connect again")
    granted_scope = str(tokens.get("scope", ""))
    if drive.DRIVE_SCOPE not in granted_scope.split():
        raise HTTPException(status_code=409, detail="Google Drive file permission was not granted; connect again and approve selected-file access")
    encrypted = drive.encrypt_refresh_token(settings, refresh_token)
    with connection() as database:
        database.execute(
            """INSERT INTO google_drive_connections
                   (actor_login, refresh_token_ciphertext, granted_scope)
               VALUES (%s, %s, %s)
               ON CONFLICT (actor_login) DO UPDATE SET
                   refresh_token_ciphertext = EXCLUDED.refresh_token_ciphertext,
                   granted_scope = EXCLUDED.granted_scope,
                   connected_at = now(), updated_at = now()""",
            (actor, encrypted, granted_scope),
        )
    return RedirectResponse(settings.google_drive_app_origin + "/library?drive=connected", status_code=303)


@router.delete("/connection")
def disconnect(
    x_gm_user_role: str | None = Header(default=None),
    x_gm_user_login: str | None = Header(default=None),
) -> dict[str, bool]:
    actor = _owner(x_gm_user_role, x_gm_user_login)
    with connection() as database:
        active = database.execute(
            """SELECT count(*)::integer AS count FROM google_drive_imports drive_import
               JOIN google_drive_connections account ON account.id = drive_import.connection_id
               WHERE account.actor_login = %s AND drive_import.status IN ('pending', 'downloading')""",
            (actor,),
        ).fetchone()
        if active and active["count"]:
            raise HTTPException(status_code=409, detail="wait for active Drive imports to finish before disconnecting")
        result = database.execute(
            "DELETE FROM google_drive_connections WHERE actor_login = %s", (actor,)
        )
    return {"disconnected": bool(result.rowcount)}


@router.get("/picker-token")
def picker_token(
    response: Response,
    x_gm_user_role: str | None = Header(default=None),
    x_gm_user_login: str | None = Header(default=None),
) -> dict[str, str]:
    actor = _owner(x_gm_user_role, x_gm_user_login)
    settings = _require_configuration()
    saved = _connection_for(actor)
    try:
        refresh = drive.decrypt_refresh_token(settings, saved["refresh_token_ciphertext"])
        access = drive.refresh_access_token(settings, refresh)
    except drive.GoogleDriveError as error:
        raise HTTPException(status_code=409 if error.reconnect else 502, detail=str(error)) from error
    response.headers["Cache-Control"] = "no-store"
    return {
        "access_token": access,
        "developer_key": settings.google_drive_api_key.get_secret_value(),
        "app_id": settings.google_drive_app_id,
    }


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_ids: list[str] = Field(min_length=1, max_length=200)
    batch_name: str = Field(default="Google Drive imports", min_length=1, max_length=160)
    collection_id: UUID | None = None
    name_prefix: str | None = Field(default=None, min_length=1, max_length=230)
    media_role: Literal["auto", "talking", "broll"] = "auto"

    @field_validator("file_ids")
    @classmethod
    def selected_once(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("select each Drive file once")
        if any(not drive.FILE_ID.fullmatch(value) for value in values):
            raise ValueError("invalid Google Drive file selection")
        return values

    @field_validator("batch_name", "name_prefix")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned or "\x00" in cleaned:
            raise ValueError("enter a valid name")
        return cleaned


def _safe_name(value: Any, identifier: str) -> str:
    name = " ".join(str(value or "").replace("\x00", "").split())
    return (name or f"Drive file {identifier[:12]}")[:255]


@router.post("/imports")
def create_imports(
    payload: ImportRequest,
    x_gm_user_role: str | None = Header(default=None),
    x_gm_user_login: str | None = Header(default=None),
) -> dict[str, Any]:
    actor = _owner(x_gm_user_role, x_gm_user_login)
    settings = _require_configuration()
    saved = _connection_for(actor)
    try:
        refresh = drive.decrypt_refresh_token(settings, saved["refresh_token_ciphertext"])
        access = drive.refresh_access_token(settings, refresh)
        metadata = [drive.file_metadata(access, identifier) for identifier in payload.file_ids]
    except drive.GoogleDriveError as error:
        raise HTTPException(status_code=409 if error.reconnect else 502, detail=str(error)) from error

    prepared: list[dict[str, Any]] = []
    for item in metadata:
        mime_type = str(item.get("mimeType", "")).lower()
        if not mime_type.startswith(("video/", "image/", "audio/")):
            raise HTTPException(status_code=422, detail=f"{_safe_name(item.get('name'), item['id'])} is not supported media")
        try:
            byte_size = int(item.get("size", 0))
        except (TypeError, ValueError) as error:
            raise HTTPException(status_code=422, detail="a selected Drive file has no downloadable size") from error
        if byte_size <= 0 or byte_size > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail=f"{_safe_name(item.get('name'), item['id'])} exceeds the import size limit or is empty")
        if item.get("trashed") or not item.get("capabilities", {}).get("canDownload", False):
            raise HTTPException(status_code=422, detail=f"{_safe_name(item.get('name'), item['id'])} cannot be downloaded")
        remote_version = str(item.get("md5Checksum") or f"{item.get('modifiedTime', '')}:{byte_size}")
        prepared.append({**item, "mime_type": mime_type, "byte_size": byte_size, "remote_version": remote_version})

    project_id = uuid4()
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    with connection() as database:
        if payload.collection_id is not None:
            folder = database.execute(
                "SELECT id FROM library_collections WHERE id = %s FOR KEY SHARE", (payload.collection_id,)
            ).fetchone()
            if folder is None:
                raise HTTPException(status_code=409, detail="destination folder no longer exists; choose another folder")
        existing = database.execute(
            """SELECT drive_import.id, drive_import.asset_id, drive_import.remote_file_id,
                      drive_import.remote_version, drive_import.status, assets.status AS asset_status
               FROM google_drive_imports drive_import
               JOIN assets ON assets.id = drive_import.asset_id
               WHERE drive_import.connection_id = %s AND drive_import.remote_file_id = ANY(%s)""",
            (saved["id"], payload.file_ids),
        ).fetchall()
        by_remote = {(str(row["remote_file_id"]), str(row["remote_version"])): row for row in existing}
        new_items = [item for item in prepared if (item["id"], item["remote_version"]) not in by_remote]
        if new_items:
            database.execute(
                """INSERT INTO projects (id, name, brief, privacy_mode, ai_copy_allowed)
                   VALUES (%s, %s, '', 'local_only', false)""",
                (project_id, payload.batch_name),
            )
        for index, item in enumerate(prepared, 1):
            old = by_remote.get((item["id"], item["remote_version"]))
            if old is not None:
                old_item = {"id": old["id"], "asset_id": old["asset_id"], "remote_name": _safe_name(item.get("name"), item["id"])}
                if old["status"] == "failed" or old["asset_status"] == "failed":
                    database.execute(
                        """UPDATE google_drive_imports SET status = 'pending', attempts = 0,
                               next_attempt_at = now(), lease_expires_at = NULL, error = NULL,
                               updated_at = now() WHERE id = %s""",
                        (old["id"],),
                    )
                    database.execute(
                        """UPDATE assets SET status = 'uploading',
                               metadata = metadata - 'google_drive_import_error' - 'finalize_error',
                               updated_at = now() WHERE id = %s AND status = 'failed'""",
                        (old["asset_id"],),
                    )
                    created.append(old_item)
                else:
                    skipped.append(old_item)
                continue
            asset_id, import_id = uuid4(), uuid4()
            source_name = _safe_name(item.get("name"), item["id"])
            display_name = f"{payload.name_prefix} {index:03d}" if payload.name_prefix else None
            role = payload.media_role if item["mime_type"].startswith("video/") else "auto"
            database.execute(
                """INSERT INTO assets
                       (id, project_id, source_name, storage_key, mime_type, byte_size, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (asset_id, project_id, source_name, f"{project_id}/{asset_id}", item["mime_type"],
                 item["byte_size"], Jsonb({"import_provider": "google_drive", "remote_file_id": item["id"]})),
            )
            if payload.collection_id is not None:
                database.execute(
                    "INSERT INTO library_collection_assets (collection_id, asset_id) VALUES (%s, %s)",
                    (payload.collection_id, asset_id),
                )
            preferences = {"collection_id": str(payload.collection_id) if payload.collection_id else None,
                           "display_name": display_name, "media_role": role}
            database.execute(
                "INSERT INTO asset_library_metadata (asset_id, display_name, media_role) VALUES (%s, %s, %s)",
                (asset_id, display_name, role),
            )
            database.execute(
                "INSERT INTO library_intakes (asset_id, preferences) VALUES (%s, %s)",
                (asset_id, Jsonb(preferences)),
            )
            database.execute(
                """INSERT INTO google_drive_imports
                       (id, connection_id, asset_id, remote_file_id, remote_version, remote_name,
                        remote_modified_at, remote_md5)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (import_id, saved["id"], asset_id, item["id"], item["remote_version"], source_name,
                 item.get("modifiedTime"), item.get("md5Checksum")),
            )
            created.append({"id": import_id, "asset_id": asset_id, "remote_name": source_name})

    if created:
        try:
            client = Redis.from_url(settings.redis_url, socket_connect_timeout=2)
            client.rpush(settings.worker_queue, json.dumps({"type": "google_drive_import"}))
            client.close()
        except Exception:
            pass
    return {"items": [*created, *skipped], "created": len(created), "already_imported": len(skipped)}


@router.get("/imports")
def list_imports(
    ids: list[UUID] = Query(min_length=1, max_length=100),
    x_gm_user_role: str | None = Header(default=None),
    x_gm_user_login: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    actor = _owner(x_gm_user_role, x_gm_user_login)
    with connection() as database:
        rows = database.execute(
            """SELECT drive_import.id, drive_import.asset_id, drive_import.remote_name, drive_import.downloaded_bytes,
                      assets.byte_size, drive_import.error,
                      CASE WHEN drive_import.status = 'failed' OR assets.status = 'failed' OR ingest.status = 'failed' OR catalog.status = 'failed' THEN 'failed'
                           WHEN assets.status = 'ready' AND ingest.status = 'ready' AND catalog.status = 'ready' THEN 'ready'
                           WHEN assets.status = 'ready' THEN 'processing'
                           WHEN drive_import.status = 'downloading' THEN 'downloading'
                           ELSE 'queued' END AS status
               FROM google_drive_imports drive_import
               JOIN google_drive_connections account ON account.id = drive_import.connection_id
               JOIN assets ON assets.id = drive_import.asset_id
               LEFT JOIN asset_ingests ingest ON ingest.asset_id = assets.id
               LEFT JOIN asset_catalogs catalog ON catalog.asset_id = assets.id
               WHERE account.actor_login = %s AND drive_import.id = ANY(%s)
               ORDER BY drive_import.created_at, drive_import.id""",
            (actor, ids),
        ).fetchall()
    return list(rows)
