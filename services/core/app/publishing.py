"""Owner-approved publishing of immutable final exports, with durable remote stages."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import get_settings
from app.database import connection
from app.media_analysis import resolve_source
from app.productization import actor_login, require_owner, _audit
from app import meta_publishing as meta

router = APIRouter(prefix="/api/v1/publishing", tags=["publishing"])
ACTIVE = ("queued", "uploading", "processing", "publishing", "unknown")
SCOPES = "pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,instagram_content_publish"
POST_FIELDS = "p.id,p.draft_id,p.connection_id,p.approval_request_id,p.approved_revision,p.approved_by,p.publish_at,p.status,p.remote_container_id,p.remote_media_id,p.publish_started_at,p.permalink,p.error,p.created_at,p.updated_at,c.platform,c.display_name AS account_name"


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OAuthComplete(Closed):
    code: str = Field(min_length=1, max_length=4096)
    state: str = Field(min_length=32, max_length=200)


class DraftCreate(Closed):
    id: UUID
    final_export_id: UUID


class DraftUpdate(Closed):
    revision: int = Field(ge=1)
    caption: str = Field(max_length=2200)


class ResolveUnknown(Closed):
    account_checked_no_post: bool


class PublishRequest(Closed):
    request_id: UUID
    revision: int = Field(ge=1)
    connection_ids: list[UUID] = Field(min_length=1, max_length=4)
    publish_at: datetime | None = None

    @field_validator("connection_ids")
    @classmethod
    def unique(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("choose each account only once")
        return value

    @field_validator("publish_at")
    @classmethod
    def aware(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("include the posting timezone")
        return value


def owner(header):
    actor = actor_login(header)
    require_owner(actor)
    return actor


def configured(settings) -> bool:
    return bool(
        settings.meta_publishing_enabled
        and settings.meta_app_id
        and settings.meta_app_secret.get_secret_value()
        and settings.meta_app_origin
        and settings.meta_token_encryption_key.get_secret_value()
    )


def require_configured(settings):
    if not configured(settings):
        raise HTTPException(
            503,
            "Meta publishing is not configured. Open Publishing for setup instructions.",
        )
    meta.cipher(settings)


def redirect_uri(settings) -> str:
    return settings.meta_app_origin.rstrip("/") + "/publishing/connect"


def digest_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def export_row(database, export_id, *, lock=False):
    row = database.execute(
        """SELECT f.*,r.version,r.approved_at,ep.document,j.project_id,pr.name AS project_name,
        pr.brief,pr.ai_copy_allowed FROM final_exports f JOIN edit_runs r ON r.id=f.edit_run_id
        JOIN edit_plans ep ON ep.id=r.edit_plan_id JOIN jobs j ON j.id=f.job_id
        JOIN projects pr ON pr.id=j.project_id WHERE f.id=%s"""
        + (" FOR UPDATE OF f" if lock else ""),
        (export_id,),
    ).fetchone()
    if (
        not row
        or row["status"] != "ready"
        or not row["approved_at"]
        or not row.get("video_path")
    ):
        raise HTTPException(
            409,
            "Choose a completed, approved final export. Previews cannot be published.",
        )
    return row


def export_file(settings, row) -> tuple[Path, str]:
    try:
        path = resolve_source(settings.media_root, row["video_path"])
        size = path.stat().st_size
        if size <= 0 or size > 1_000_000_000:
            raise ValueError("size")
        render = (row.get("manifest") or {}).get("render") or {}
        if render.get("width") != 1080 or render.get("height") != 1920:
            raise ValueError("vertical")
        return path, digest_file(path)
    except (OSError, ValueError):
        raise HTTPException(
            409,
            "Publishing requires an available full-quality vertical MP4 under 1 GB. Rebuild or create a vertical export.",
        ) from None


def _draft(database, draft_id, *, lock=False):
    row = database.execute(
        "SELECT * FROM publishing_drafts WHERE id=%s" + (" FOR UPDATE" if lock else ""),
        (draft_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Posting draft not found.")
    return row


def _posts(database, draft_id):
    return list(
        database.execute(
            f"SELECT {POST_FIELDS} FROM publishing_posts p JOIN social_connections c ON c.id=p.connection_id WHERE p.draft_id=%s ORDER BY p.created_at,c.platform",
            (draft_id,),
        ).fetchall()
    )


def _public_draft(database, row):
    export = database.execute(
        "SELECT f.job_id,r.version,pr.name AS project_name FROM final_exports f JOIN edit_runs r ON r.id=f.edit_run_id JOIN jobs j ON j.id=f.job_id JOIN projects pr ON pr.id=j.project_id WHERE f.id=%s",
        (row["final_export_id"],),
    ).fetchone()
    captions = database.execute(
        "SELECT id,status,options,error,total_tokens FROM publishing_caption_requests WHERE draft_id=%s ORDER BY created_at DESC LIMIT 1",
        (row["id"],),
    ).fetchone()
    return {
        **row,
        **(export or {}),
        "posts": _posts(database, row["id"]),
        "caption_request": captions,
    }


@router.get("/status")
def publishing_status(x_gm_user_login: str | None = Header(default=None)):
    owner(x_gm_user_login)
    settings = get_settings()
    ready = configured(settings)
    if ready:
        try:
            meta.cipher(settings)
        except meta.MetaError:
            ready = False
    return {
        "configured": ready,
        "graph_version": settings.meta_graph_version,
        "redirect_uri": redirect_uri(settings) if settings.meta_app_origin else None,
        "setup_command": "python3 scripts/configure-meta-publishing.py",
        "platforms": ["instagram", "facebook"],
        "publishes_previews": False,
    }


@router.get("/connections")
def list_connections(x_gm_user_login: str | None = Header(default=None)):
    owner(x_gm_user_login)
    with connection() as database:
        return list(
            database.execute(
                "SELECT id,platform,external_id,display_name,active,token_expires_at,updated_at FROM social_connections ORDER BY platform,display_name"
            ).fetchall()
        )


@router.post("/meta/start")
def start_meta(x_gm_user_login: str | None = Header(default=None)):
    actor = owner(x_gm_user_login)
    settings = get_settings()
    require_configured(settings)
    state = secrets.token_urlsafe(40)
    with connection() as database:
        database.execute("DELETE FROM social_oauth_states WHERE expires_at<now()")
        database.execute(
            "INSERT INTO social_oauth_states(state_hash,actor_login,expires_at) VALUES (%s,%s,now()+interval '10 minutes')",
            (hashlib.sha256(state.encode()).hexdigest(), actor),
        )
    values = {
        "client_id": settings.meta_app_id,
        "redirect_uri": redirect_uri(settings),
        "state": state,
        "response_type": "code",
    }
    if settings.meta_login_config_id:
        values["config_id"] = settings.meta_login_config_id
    else:
        values.update(scope=SCOPES, auth_type="rerequest")
    return {
        "url": f"https://www.facebook.com/{settings.meta_graph_version}/dialog/oauth?"
        + urlencode(values)
    }


@router.post("/meta/complete")
def complete_meta(
    payload: OAuthComplete, x_gm_user_login: str | None = Header(default=None)
):
    actor = owner(x_gm_user_login)
    settings = get_settings()
    require_configured(settings)
    with connection() as database:
        state = database.execute(
            "DELETE FROM social_oauth_states WHERE state_hash=%s AND actor_login=%s AND expires_at>now() RETURNING state_hash",
            (hashlib.sha256(payload.state.encode()).hexdigest(), actor),
        ).fetchone()
    if not state:
        raise HTTPException(
            409,
            "This connection request expired or was already used. Start Connect Meta again.",
        )
    try:
        result = meta.api(
            settings,
            "oauth/access_token",
            params={
                "client_id": settings.meta_app_id,
                "client_secret": settings.meta_app_secret.get_secret_value(),
                "redirect_uri": redirect_uri(settings),
                "code": payload.code,
            },
        )
        short = result["access_token"]
        result = meta.api(
            settings,
            "oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": settings.meta_app_id,
                "client_secret": settings.meta_app_secret.get_secret_value(),
                "fb_exchange_token": short,
            },
        )
        token = result["access_token"]
        expires = datetime.now(timezone.utc) + timedelta(
            seconds=max(60, min(int(result.get("expires_in") or 5_184_000), 5_184_000))
        )
        permissions = meta.api(settings, "me/permissions", token=token).get("data", [])
        granted = {p["permission"] for p in permissions if p.get("status") == "granted"}
        required = {
            "pages_show_list",
            "pages_read_engagement",
            "instagram_basic",
            "instagram_content_publish",
            "pages_manage_posts",
        }
        if not required <= granted:
            raise meta.MetaError(
                "Meta did not grant all requested publishing permissions. Check app use cases and reconnect."
            )
        pages, after = [], None
        for _ in range(5):
            params = {
                "fields": "id,name,access_token,tasks,instagram_business_account{id,username}",
                "limit": 100,
            }
            if after:
                params["after"] = after
            result = meta.api(settings, "me/accounts", token=token, params=params)
            pages.extend(result.get("data", []))
            after = (
                ((result.get("paging") or {}).get("cursors") or {}).get("after")
                if (result.get("paging") or {}).get("next")
                else None
            )
            if not after:
                break
        accounts = []
        for page in pages:
            if not set(page.get("tasks") or []) & {
                "CREATE_CONTENT",
                "MANAGE",
                "PROFILE_PLUS_CREATE_CONTENT",
                "PROFILE_PLUS_FULL_CONTROL",
                "PROFILE_PLUS_FACEBOOK_ACCESS",
            }:
                continue
            encrypted = meta.encrypt_token(settings, page["access_token"])
            accounts.append(
                ("facebook", meta.identifier(page["id"]), page["name"], encrypted)
            )
            instagram = page.get("instagram_business_account")
            if instagram:
                accounts.append(
                    (
                        "instagram",
                        meta.identifier(instagram["id"]),
                        instagram.get("username") or page["name"],
                        encrypted,
                    )
                )
        if not accounts:
            raise meta.MetaError(
                "No publishable Facebook Page or linked professional Instagram account was returned. Check your Page access and account link."
            )
        with connection() as database:
            for platform, external, name, encrypted in accounts:
                database.execute(
                    """INSERT INTO social_connections(platform,external_id,display_name,token_ciphertext,token_expires_at,connected_by)
                    VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(platform,external_id) DO UPDATE SET display_name=EXCLUDED.display_name,
                    token_ciphertext=EXCLUDED.token_ciphertext,token_expires_at=EXCLUDED.token_expires_at,active=true,connected_by=EXCLUDED.connected_by,updated_at=now()""",
                    (platform, external, name, encrypted, expires, actor),
                )
            _audit(
                database,
                actor,
                "publishing.accounts_connected",
                "studio",
                "primary",
                {"accounts": len(accounts)},
            )
        return {"connected": len(accounts)}
    except (meta.MetaError, KeyError, ValueError, TypeError) as error:
        detail = (
            str(error)
            if isinstance(error, meta.MetaError)
            else "Meta returned incomplete account details. Reconnect the account."
        )
        raise HTTPException(409, detail) from None


@router.delete("/connections/{connection_id}")
def disconnect(connection_id: UUID, x_gm_user_login: str | None = Header(default=None)):
    actor = owner(x_gm_user_login)
    with connection() as database:
        database.execute(
            "UPDATE social_connections SET active=false,token_ciphertext='',updated_at=now() WHERE id=%s",
            (connection_id,),
        )
        database.execute(
            "UPDATE publishing_posts SET status='cancelled',error='Account disconnected',updated_at=now() WHERE connection_id=%s AND status='queued'",
            (connection_id,),
        )
        _audit(
            database,
            actor,
            "publishing.account_disconnected",
            "connection",
            str(connection_id),
        )
    return {"disconnected": True}


@router.get("/drafts")
def list_drafts(
    final_export_id: UUID | None = None,
    x_gm_user_login: str | None = Header(default=None),
):
    owner(x_gm_user_login)
    with connection() as database:
        rows = database.execute(
            "SELECT * FROM publishing_drafts WHERE (%s::uuid IS NULL OR final_export_id=%s) ORDER BY created_at DESC LIMIT 50",
            (final_export_id, final_export_id),
        ).fetchall()
        return [_public_draft(database, row) for row in rows]


@router.get("/exports/{export_id}/video")
def approved_video(export_id: UUID, x_gm_user_login: str | None = Header(default=None)):
    owner(x_gm_user_login)
    with connection() as database:
        export = export_row(database, export_id)
    try:
        path = resolve_source(get_settings().media_root, export["video_path"])
    except (OSError, ValueError):
        raise HTTPException(
            404, "This final export is unavailable. Rebuild it before posting."
        ) from None
    return FileResponse(
        path, media_type="video/mp4", headers={"cache-control": "no-store"}
    )


@router.post("/drafts")
def create_draft(
    payload: DraftCreate, x_gm_user_login: str | None = Header(default=None)
):
    actor = owner(x_gm_user_login)
    with connection() as database:
        existing = database.execute(
            "SELECT * FROM publishing_drafts WHERE id=%s", (payload.id,)
        ).fetchone()
        if existing:
            if str(existing["final_export_id"]) != str(payload.final_export_id):
                raise HTTPException(
                    409, "This draft request belongs to a different export."
                )
            return _public_draft(database, existing)
        export = export_row(database, payload.final_export_id, lock=True)
        _, sha = export_file(get_settings(), export)
        row = database.execute(
            "INSERT INTO publishing_drafts(id,final_export_id,video_sha256,caption,created_by) VALUES (%s,%s,%s,%s,%s) RETURNING *",
            (
                payload.id,
                payload.final_export_id,
                sha,
                str(export["document"].get("post_copy") or "")[:2200],
                actor,
            ),
        ).fetchone()
        return _public_draft(database, row)


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: UUID, x_gm_user_login: str | None = Header(default=None)):
    owner(x_gm_user_login)
    with connection() as database:
        return _public_draft(database, _draft(database, draft_id))


@router.patch("/drafts/{draft_id}")
def edit_draft(
    draft_id: UUID,
    payload: DraftUpdate,
    x_gm_user_login: str | None = Header(default=None),
):
    owner(x_gm_user_login)
    with connection() as database:
        row = _draft(database, draft_id, lock=True)
        if row["revision"] != payload.revision or _posts(database, draft_id):
            raise HTTPException(
                409,
                "This draft changed or has already been approved for posting. Refresh it; create a new draft for different copy.",
            )
        row = database.execute(
            "UPDATE publishing_drafts SET caption=%s,revision=revision+1,updated_at=now() WHERE id=%s RETURNING *",
            (payload.caption, draft_id),
        ).fetchone()
        return _public_draft(database, row)


@router.post("/drafts/{draft_id}/publish")
def approve_post(
    draft_id: UUID,
    payload: PublishRequest,
    x_gm_user_login: str | None = Header(default=None),
):
    actor = owner(x_gm_user_login)
    settings = get_settings()
    require_configured(settings)
    when = payload.publish_at or datetime.now(timezone.utc)
    if when > datetime.now(timezone.utc) + timedelta(days=30) or when < datetime.now(
        timezone.utc
    ) - timedelta(minutes=2):
        raise HTTPException(422, "Choose a posting time within the next 30 days.")
    with connection() as database:
        draft = _draft(database, draft_id, lock=True)
        previous = _posts(database, draft_id)
        if previous:
            if (
                len(previous) == len(payload.connection_ids)
                and {str(p["connection_id"]) for p in previous}
                == {str(i) for i in payload.connection_ids}
                and all(
                    str(p["approval_request_id"]) == str(payload.request_id)
                    and p["approved_revision"] == payload.revision
                    for p in previous
                )
            ):
                return _public_draft(database, draft)
            raise HTTPException(
                409,
                "This draft already has posting records. Check their status before creating another post.",
            )
        if draft["revision"] != payload.revision:
            raise HTTPException(
                409, "The caption changed. Review the current draft before posting."
            )
        export = export_row(database, draft["final_export_id"], lock=True)
        _, sha = export_file(settings, export)
        if sha != draft["video_sha256"]:
            raise HTTPException(
                409, "The export changed. Create and review a new posting draft."
            )
        accounts = database.execute(
            "SELECT * FROM social_connections WHERE id=ANY(%s) ORDER BY id FOR UPDATE",
            (payload.connection_ids,),
        ).fetchall()
        if len(accounts) != len(payload.connection_ids) or any(
            not c["active"] or (c["token_expires_at"] and c["token_expires_at"] <= when)
            for c in accounts
        ):
            raise HTTPException(
                409, "A selected account needs reconnecting before this posting time."
            )
        for account in accounts:
            validate_platform_rights(export, account["platform"])
            database.execute(
                """INSERT INTO publishing_posts(draft_id,connection_id,approval_request_id,approved_revision,approved_by,publish_at,next_check_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (
                    draft_id,
                    account["id"],
                    payload.request_id,
                    payload.revision,
                    actor,
                    when,
                    when,
                ),
            )
        _audit(
            database,
            actor,
            "publishing.approved",
            "draft",
            str(draft_id),
            {
                "export_id": str(draft["final_export_id"]),
                "video_sha256": sha,
                "revision": draft["revision"],
                "accounts": [str(c["id"]) for c in accounts],
                "publish_at": when.isoformat(),
            },
        )
        return _public_draft(database, draft)


def validate_platform_rights(export, platform):
    manifest = export.get("manifest") or {}
    for item in [manifest.get("music"), *manifest.get("creative_effects", [])]:
        if not item:
            continue
        platforms = item.get("allowed_platforms")
        if platforms is None and item.get("asset_id"):
            # Historical effect manifests did not snapshot platform permissions.
            with connection() as database:
                rights = database.execute(
                    "SELECT allowed_platforms FROM creative_assets WHERE id=%s AND commercial_use=true AND synthetic_media=false",
                    (item["asset_id"],),
                ).fetchone()
            platforms = rights["allowed_platforms"] if rights else []
        if not ({"all_social", platform} & set(platforms or [])):
            raise HTTPException(
                409,
                "This export contains music or effects without recorded permission for the selected platform. Create a compatible export.",
            )


@router.post("/posts/{post_id}/cancel")
def cancel_post(post_id: UUID, x_gm_user_login: str | None = Header(default=None)):
    actor = owner(x_gm_user_login)
    with connection() as database:
        row = database.execute(
            "UPDATE publishing_posts SET status='cancelled',updated_at=now() WHERE id=%s AND status='queued' RETURNING id",
            (post_id,),
        ).fetchone()
        if not row:
            raise HTTPException(
                409,
                "Only a queued post can be cancelled. A processing or published post must be checked on the platform.",
            )
        _audit(database, actor, "publishing.cancelled", "post", str(post_id))
    return {"cancelled": True}


@router.post("/posts/{post_id}/check")
def check_post(post_id: UUID, x_gm_user_login: str | None = Header(default=None)):
    owner(x_gm_user_login)
    with connection() as database:
        row = database.execute(
            "UPDATE publishing_posts SET status=CASE WHEN status='unknown' THEN CASE WHEN publish_started_at IS NULL THEN 'processing' ELSE 'publishing' END ELSE status END,next_check_at=now(),lease_expires_at=NULL,error=NULL,updated_at=now() WHERE id=%s AND status IN ('unknown','processing','publishing') AND remote_container_id IS NOT NULL AND (lease_expires_at IS NULL OR lease_expires_at<now()) RETURNING id",
            (post_id,),
        ).fetchone()
    if not row:
        raise HTTPException(
            409,
            "No checkable remote upload is available, or a worker is currently checking it. Inspect the account before creating a new post.",
        )
    return {"checking": True}


@router.post("/posts/{post_id}/resolve-unpublished")
def resolve_unpublished(
    post_id: UUID,
    payload: ResolveUnknown,
    x_gm_user_login: str | None = Header(default=None),
):
    actor = owner(x_gm_user_login)
    if payload.account_checked_no_post is not True:
        raise HTTPException(
            422,
            "Check the destination account before marking this attempt unpublished.",
        )
    with connection() as database:
        row = database.execute(
            "UPDATE publishing_posts SET status='failed',error='Owner checked the destination account and marked this attempt unpublished.',lease_expires_at=NULL,updated_at=now() WHERE id=%s AND status='unknown' AND (lease_expires_at IS NULL OR lease_expires_at<now()) RETURNING id",
            (post_id,),
        ).fetchone()
        if not row:
            raise HTTPException(
                409, "Only an uncertain, inactive attempt can be resolved this way."
            )
        _audit(database, actor, "publishing.resolved_unpublished", "post", str(post_id))
    return {"resolved": True, "published": False}


def recover_interrupted_publishing():
    with connection() as database:
        # A write may have succeeded before a lost response. Never repeat it.
        database.execute(
            "UPDATE publishing_posts SET status='unknown',error='Publishing was interrupted; check remote status before trying anything again.',lease_expires_at=NULL,updated_at=now() WHERE status IN ('uploading','publishing') AND lease_expires_at<now()"
        )
        database.execute(
            "UPDATE publishing_posts SET lease_expires_at=NULL WHERE status='processing' AND lease_expires_at<now()"
        )
        database.execute(
            "UPDATE publishing_caption_requests SET status='failed',error='Caption generation was interrupted; no automatic AI retry was made.',lease_expires_at=NULL,updated_at=now() WHERE status='generating' AND lease_expires_at<now()"
        )


def _save_post(post_id, **values):
    allowed = {
        "status",
        "remote_container_id",
        "remote_media_id",
        "publish_started_at",
        "upload_uri",
        "permalink",
        "error",
        "next_check_at",
        "lease_expires_at",
        "checks",
    }
    if not values.keys() <= allowed:
        raise ValueError("invalid publishing update")
    with connection() as database:
        database.execute(
            "UPDATE publishing_posts SET "
            + ",".join(f"{key}=%s" for key in values)
            + ",updated_at=now() WHERE id=%s",
            (*values.values(), post_id),
        )


def process_one_post(state) -> bool:
    settings = get_settings()
    if not configured(settings):
        return False
    with connection() as database:
        post = database.execute("""SELECT p.*,d.caption,d.final_export_id,d.video_sha256,c.platform,c.external_id,c.token_ciphertext,c.active,c.token_expires_at
            FROM publishing_posts p JOIN publishing_drafts d ON d.id=p.draft_id JOIN social_connections c ON c.id=p.connection_id
            WHERE p.status IN ('queued','processing','publishing') AND p.publish_at<=now() AND p.next_check_at<=now()
            AND (p.lease_expires_at IS NULL OR p.lease_expires_at<now()) ORDER BY p.next_check_at LIMIT 1 FOR UPDATE OF p SKIP LOCKED""").fetchone()
        if not post:
            return False
        database.execute(
            "UPDATE publishing_posts SET lease_expires_at=now()+interval '20 minutes',status=CASE WHEN status='queued' THEN 'uploading' ELSE status END WHERE id=%s",
            (post["id"],),
        )
    state.active_publishing_post_id = str(post["id"])
    publication_may_exist = post["status"] == "publishing" or bool(
        post.get("publish_started_at")
    )
    try:
        if not post["active"] or (
            post["token_expires_at"]
            and post["token_expires_at"] <= datetime.now(timezone.utc)
        ):
            raise meta.MetaError(
                "Reconnect this account before posting.", reconnect=True
            )
        token = meta.decrypt_token(settings, post["token_ciphertext"])
        if post["status"] == "queued":
            with connection() as database:
                export = export_row(database, post["final_export_id"])
            path, sha = export_file(settings, export)
            if sha != post["video_sha256"]:
                raise meta.MetaError(
                    "The approved export changed; no video was uploaded."
                )
            validate_platform_rights(export, post["platform"])
            post["cover_time_seconds"] = (
                (export.get("manifest") or {}).get("creative_direction") or {}
            ).get("cover_time_seconds", 0)
            container, uri = meta.begin_upload(settings, post, token)
            _save_post(post["id"], remote_container_id=container, upload_uri=uri)
            meta.upload_file(uri, path, token)
            _save_post(
                post["id"],
                status="processing",
                next_check_at=datetime.now(timezone.utc) + timedelta(seconds=60),
                lease_expires_at=None,
            )
        else:
            remote = meta.processing_status(settings, post, token)
            if remote == "failed":
                raise meta.MetaError(
                    "Meta could not process this video. Check the account and video requirements."
                )
            if remote == "published":
                link = None
                try:
                    link = meta.permalink(settings, post, token)
                except meta.MetaError:
                    pass
                _save_post(
                    post["id"],
                    status="published",
                    permalink=link,
                    error=None,
                    lease_expires_at=None,
                )
            elif remote == "ready" and post["status"] == "processing":
                with connection() as database:
                    export = export_row(database, post["final_export_id"])
                    account = database.execute(
                        "SELECT active FROM social_connections WHERE id=%s",
                        (post["connection_id"],),
                    ).fetchone()
                if not account or not account["active"]:
                    raise meta.MetaError(
                        "The account was disconnected before publication."
                    )
                _, sha = export_file(settings, export)
                if sha != post["video_sha256"]:
                    raise meta.MetaError(
                        "The approved export changed; publication was stopped."
                    )
                _save_post(
                    post["id"],
                    status="publishing",
                    publish_started_at=datetime.now(timezone.utc),
                )  # Persist before the irreversible call.
                publication_may_exist = True
                identity = meta.publish(settings, post, token)
                post["remote_media_id"] = identity
                link = None
                try:
                    link = meta.permalink(settings, post, token)
                except meta.MetaError:
                    pass
                _save_post(
                    post["id"],
                    remote_media_id=identity,
                    status="published"
                    if post["platform"] == "instagram"
                    else "publishing",
                    permalink=link,
                    next_check_at=datetime.now(timezone.utc) + timedelta(seconds=60),
                    lease_expires_at=None,
                )
            elif post["checks"] >= 20:
                _save_post(
                    post["id"],
                    status="unknown",
                    error="Meta processing is taking longer than expected. Check status; publishing will not be repeated.",
                    lease_expires_at=None,
                )
            else:
                _save_post(
                    post["id"],
                    checks=post["checks"] + 1,
                    next_check_at=datetime.now(timezone.utc) + timedelta(seconds=60),
                    lease_expires_at=None,
                )
    except Exception as error:
        ambiguous = isinstance(error, meta.MetaError) and error.ambiguous
        # Unexpected errors after claiming a write are uncertain too.
        status = (
            "unknown"
            if publication_may_exist
            or ambiguous
            or not isinstance(error, (meta.MetaError, HTTPException))
            else "failed"
        )
        detail = (
            str(error)
            if isinstance(error, meta.MetaError)
            else str(error.detail)
            if isinstance(error, HTTPException)
            else "Publishing could not be verified. Check the remote account before trying again."
        )
        _save_post(post["id"], status=status, error=detail[:400], lease_expires_at=None)
    finally:
        state.active_publishing_post_id = None
    return True
