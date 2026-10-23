import hmac
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from redis import Redis

from app.config import get_settings
from app.database import connection
from app.uploads import parse_upload_hook


router = APIRouter(prefix="/api/v1", tags=["uploads"])


@router.post("/upload-hooks")
def receive_upload_hook(
    payload: dict[str, Any],
    token: str = Query(default=""),
) -> dict[str, Any]:
    settings = get_settings()
    if not hmac.compare_digest(token, settings.upload_hook_secret):
        raise HTTPException(status_code=401, detail="invalid upload hook token")

    try:
        facts = parse_upload_hook(payload)
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    status_for_event = {
        "post-create": "uploading",
        "post-finish": "uploaded",
        "post-terminate": "failed",
    }.get(facts.event_type)

    if facts.event_type == "pre-create":
        with connection() as database:
            asset = database.execute(
                """
                SELECT byte_size, mime_type, status
                FROM assets
                WHERE id = %s AND project_id = %s
                """,
                (facts.asset_id, facts.project_id),
            ).fetchone()
        if asset is None:
            return reject_upload("registered asset not found", 404)
        if asset["status"] != "uploading":
            return reject_upload("asset is not accepting an upload", 409)
        if facts.byte_size <= 0 or facts.byte_size != asset["byte_size"]:
            return reject_upload("upload size does not match the registered asset", 400)
        if facts.byte_size > settings.max_upload_bytes:
            return reject_upload("upload exceeds the configured limit", 413)
        if facts.mime_type != asset["mime_type"]:
            return reject_upload("upload media type does not match the registered asset", 400)
        return {
            "ChangeFileInfo": {
                "ID": str(facts.asset_id),
                "MetaData": {
                    "assetId": str(facts.asset_id),
                    "projectId": str(facts.project_id),
                    "filetype": facts.mime_type,
                },
            }
        }

    if status_for_event is None:
        return {}

    allowed_statuses = {
        "post-create": ["uploading"],
        "post-finish": ["uploading", "uploaded"],
        "post-terminate": ["uploading", "uploaded"],
    }[facts.event_type]

    with connection() as database:
        row = database.execute(
            """
            UPDATE assets
            SET status = %s,
                tus_upload_id = %s,
                tus_storage_key = %s,
                byte_size = CASE WHEN %s > 0 THEN %s ELSE byte_size END,
                updated_at = now()
            WHERE id = %s AND project_id = %s AND status = ANY(%s)
            RETURNING id
            """,
            (
                status_for_event,
                facts.upload_id,
                facts.storage_key,
                facts.byte_size,
                facts.byte_size,
                facts.asset_id,
                facts.project_id,
                allowed_statuses,
            ),
        ).fetchone()
        if row is None:
            current = database.execute(
                "SELECT status FROM assets WHERE id = %s AND project_id = %s",
                (facts.asset_id, facts.project_id),
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="registered asset not found")
            if facts.event_type == "post-finish" and current["status"] == "ready":
                return {}
            raise HTTPException(status_code=409, detail="asset upload state has already advanced")

    if facts.event_type == "post-finish":
        try:
            client = Redis.from_url(settings.redis_url, socket_connect_timeout=2)
            client.rpush(
                settings.worker_queue,
                json.dumps({"type": "finalize_upload", "asset_id": str(facts.asset_id)}),
            )
            client.close()
        except Exception:
            # The worker also sweeps PostgreSQL, so Redis notification failure
            # must not make tusd retry an otherwise durable completion hook.
            pass

    return {}


def reject_upload(message: str, status_code: int) -> dict[str, Any]:
    return {
        "HTTPResponse": {
            "StatusCode": status_code,
            "Body": json.dumps({"message": message}),
            "Header": {"Content-Type": "application/json"},
        },
        "RejectUpload": True,
    }
