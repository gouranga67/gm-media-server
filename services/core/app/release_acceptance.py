"""Owner-recorded, build-specific acceptance; reads never run experiments or posts."""
import json
import math
import re
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, model_validator
from redis import Redis
from redis.exceptions import RedisError

from app.build_info import deployed_build_id
from app.config import get_settings
from app.database import connection
from app.edit_plan import document_sha256
from app.learning_evidence import preview_available
from app.media_analysis import resolve_source
from app.productization import actor_login, require_owner
from app.publishing import configured
from app import meta_publishing as meta

router = APIRouter(prefix="/api/v1/release", tags=["release acceptance"])
CHECKS = (
    ("story_playback", "Downloaded final reel: story, words, colour and sound on a phone", "private", "edit", False),
    ("green_screen_playback", "Review a green-screen preview: key edges, background, captions and sound", "private", "edit", False),
    ("caption_revision", "Edit captions and make a targeted revision", "private", "edit", False),
    ("library_intake", "Import, organise and find mixed media", "private", "note", False),
    ("concurrent_work", "Upload or search while another edit renders", "private", "edit", False),
    ("access_roles", "Check an editor and viewer through private access", "private", "note", True),
    ("restore_recovery", "Review the isolated backup restore result", "private", "restore", False),
    ("reboot_recovery", "Review interrupted-render reboot recovery", "private", "reboot", False),
    ("instagram_post", "Check one approved Instagram post on the account", "publishing", "post", True),
    ("facebook_post", "Check one approved Facebook post on the Page", "publishing", "post", True),
    ("scheduled_post", "Check a deliberately scheduled post after it is due", "publishing", "post", False),
)
SPEC = {key:dict(key=key,label=label,scope=scope,evidence_kind=kind,allow_na=na) for key,label,scope,kind,na in CHECKS}
BUILD = re.compile(r"^[0-9a-f]{7,64}$")
CURRENT_SQL = """SELECT DISTINCT ON(check_key) * FROM release_observations
    WHERE build_id=%s ORDER BY check_key,created_at DESC,id DESC"""
HISTORY_SQL = """SELECT id,build_id,check_key,result,note,job_id,edit_run_id,publishing_post_id,
    recorded_by,created_at FROM release_observations ORDER BY created_at DESC,id DESC LIMIT 100"""
QUEUE_SQL = """SELECT
    (SELECT count(*) FROM edit_runs WHERE status IN ('pending','planning','rendering')) AS edits,
    (SELECT count(*) FROM asset_ingests WHERE status IN ('pending','running')) AS analysis,
    (SELECT count(*) FROM final_exports WHERE status IN ('pending','rendering')) AS exports,
    (SELECT count(*) FROM publishing_posts WHERE status IN ('queued','uploading','processing','publishing')) AS posts,
    (SELECT count(*) FROM publishing_posts WHERE status='unknown') AS uncertain_posts,
    (SELECT count(*) FROM publishing_posts WHERE status='failed') AS failed_posts"""


def read_object(path):
    try:
        if path.stat().st_size > 65536:
            return {}
        value = json.loads(path.read_text())
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):
        return {}


def fresh(value, hours, now):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return parsed.tzinfo is not None and 0 <= (now-parsed).total_seconds() <= hours*3600
    except (TypeError,ValueError):
        return False


def recovery(settings, kind, now):
    filename = "restore-verification.json" if kind == "restore" else "reboot-recovery-drill.json"
    raw = read_object(settings.appliance_status_path.parent / filename)
    passed = raw.get("status") == "passed" and fresh(raw.get("completed_at"),30*24,now)
    if kind == "reboot":
        passed = passed and raw.get("boot_id_changed") is True
    else:
        passed = passed and isinstance(raw.get("original_count"),int) and not isinstance(raw["original_count"],bool) and raw["original_count"] > 0
    # No raw command output, paths, backup keys or boot identifiers leave this reader.
    return {"status":"pass" if passed else "pending","completed_at":raw.get("completed_at"),
        "original_count":raw.get("original_count") if kind == "restore" else None,
        "method":"isolated file restore and database-dump listing" if kind == "restore" else "interrupted render across a changed boot"}


def worker_evidence(settings, now):
    result=dict(key="worker",label="Recent worker check-in",scope="private",status="pending",
        detail="The worker check-in is missing, stale or unavailable. Open Operations before starting more work.")
    client=None
    if not getattr(settings,"redis_url",None):
        return result
    try:
        client=Redis.from_url(settings.redis_url,decode_responses=True,socket_connect_timeout=2,socket_timeout=2)
        raw=client.get(settings.worker_heartbeat_key)
        value=json.loads(raw) if raw and len(raw)<=65536 else {}
        timestamp=value.get("unix_time") if isinstance(value,dict) else None
        if isinstance(timestamp,(int,float)) and not isinstance(timestamp,bool) and math.isfinite(timestamp):
            age=now.timestamp()-timestamp
            if 0 <= age <= settings.worker_heartbeat_ttl_seconds:
                result.update(status="pass",detail="A recent worker check-in was recorded. This does not prove that every active task is advancing.")
    except (RedisError,OSError,ValueError,TypeError):
        pass
    finally:
        if client:
            try:client.close()
            except (RedisError,OSError):pass
    return result


def technical_snapshot(settings, schema, accounts, queues, now):
    health = read_object(settings.appliance_status_path)
    recent = fresh(health.get("generated_at"),1/6,now)
    def section(key):
        value = health.get(key)
        return value if isinstance(value,dict) else {}
    def number(part,key,default):
        value = part.get(key)
        return value if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value >= 0 else default
    services,disk = section("services"),section("disk")
    expected = number(services,"expected",0)
    runtime = recent and expected >= 1 and number(services,"running",0) >= expected
    runtime = runtime and number(disk,"available_bytes",0) >= 50*1024**3 and number(disk,"used_percent",100) < 85
    backup,offsite = section("backup"),section("offsite_backup")
    usb_ready = recent and backup.get("state") == "ready" and fresh(backup.get("completed_at"),30,now)
    offsite_ready = recent and offsite.get("state") in ("ready","attention","running") and fresh(offsite.get("last_verified_at") or offsite.get("completed_at"),36,now)
    enabled = configured(settings)
    if enabled:
        try:
            meta.cipher(settings)
        except meta.MetaError:
            enabled = False
    connected = sum(bool(a["active"]) and (a["token_expires_at"] is None or a["token_expires_at"] > now) for a in accounts)
    records = [
        ("schema","Release database schema",schema,"private","Deploy migration 046."),
        ("private_access","Private access and owner configured",bool(settings.tailscale_auth_required and settings.tailscale_owner_login),"private","Finish private access configuration."),
        ("runtime","Recent running-service and disk snapshot",bool(runtime),"private","Open System for service/disk diagnostics; the snapshot must be under ten minutes old."),
        ("backup","Recent completed USB backup",bool(usb_ready),"private","Check the USB backup; a completed copy under 30 hours old is required."),
        ("offsite","Recent verified off-site copy",bool(offsite_ready),"private","Check off-site backup; file-size verification must be under 36 hours old."),
        ("meta","Meta app configured",enabled,"publishing","Run the existing Meta setup and reconnect in Publishing."),
        ("accounts","Unexpired connected posting account",connected>0,"publishing","Connect a publishing account. Remote permissions are verified only by a real post."),
        ("post_outcomes","No uncertain publication outcomes",queues["uncertain_posts"] == 0,"publishing","Check uncertain outcomes on the account before retrying."),
    ]
    result = [dict(key=key,label=label,status="pass" if passed else "pending",scope=scope,
        detail="Recorded locally; no external request was made." if passed else detail) for key,label,passed,scope,detail in records]
    for kind in ("restore","reboot"):
        result.append(dict(key=kind,label="Isolated restore evidence" if kind == "restore" else "Reboot recovery evidence",
            scope="private",**recovery(settings,kind,now)))
    result.append(worker_evidence(settings,now))
    return result


def outcome(checks, technical):
    def passed(item):
        record = item.get("observation") or {}
        return record.get("result") == "pass" or (item["allow_na"] and record.get("result") == "not_applicable")
    private = all(passed(c) for c in checks if c["scope"] == "private") and all(t["status"] == "pass" for t in technical if t["scope"] == "private")
    publishing = private and all(passed(c) for c in checks if c["scope"] == "publishing") and all(t["status"] == "pass" for t in technical if t["scope"] == "publishing")
    publishing = publishing and any((c.get("observation") or {}).get("result") == "pass" for c in checks if c["key"] in ("instagram_post","facebook_post"))
    return {"private_pilot_complete":private,"publishing_acceptance_complete":publishing,"public_customer_launch_ready":False}


@router.get("/readiness")
def readiness(x_gm_user_login: str | None = Header(default=None)):
    require_owner(actor_login(x_gm_user_login))
    settings,now = get_settings(),datetime.now(timezone.utc)
    build = deployed_build_id(settings)
    with connection() as database:
        schema = database.execute("SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE version='046_release_acceptance.sql') AS ready").fetchone()["ready"]
        current = list(database.execute(CURRENT_SQL,(build,)).fetchall())
        history = list(database.execute(HISTORY_SQL).fetchall())
        accounts = list(database.execute("SELECT active,token_expires_at FROM social_connections").fetchall())
        queues = database.execute(QUEUE_SQL).fetchone()
        posts = list(database.execute("""SELECT p.id,p.status,p.schedule_requested,p.publish_at,c.platform,c.display_name AS account_name,
            d.final_export_id,r.version,f.job_id FROM publishing_posts p JOIN social_connections c ON c.id=p.connection_id
            JOIN publishing_drafts d ON d.id=p.draft_id JOIN final_exports f ON f.id=d.final_export_id
            JOIN edit_runs r ON r.id=f.edit_run_id WHERE p.status='published' ORDER BY p.updated_at DESC LIMIT 50""").fetchall())
        playback = list(database.execute("""SELECT r.job_id,r.version,pr.name AS project_name,
            COALESCE(j.composition->>'mode','auto') AS composition_mode,
            r.approved_at IS NOT NULL AND EXISTS(SELECT 1 FROM final_exports f WHERE f.edit_run_id=r.id AND f.status='ready') AS has_final FROM edit_runs r
            JOIN jobs j ON j.id=r.job_id JOIN projects pr ON pr.id=j.project_id
            WHERE r.status='ready' AND j.archived_at IS NULL ORDER BY r.completed_at DESC NULLS LAST,r.id DESC LIMIT 50""").fetchall())
    technical = technical_snapshot(settings,schema,accounts,queues,now)
    if not BUILD.fullmatch(build):
        technical.append(dict(key="build",label="Known deployed build",scope="private",status="pending",detail="Deploy a committed build before recording acceptance."))
    checks = [{**spec,"observation":next((row for row in current if row["check_key"] == key),None)} for key,spec in SPEC.items()]
    return {"version":1,"build_id":build,"generated_at":now,"schema_ready":bool(schema),"checks":checks,"technical":technical,
        "history":history,"published_posts":posts,"playback_options":playback,"queues":queues,**outcome(checks,technical),
        "automatic_model_calls":0,"automatic_posts":0,"scope":"One shared private studio. Human records are attestations, not automatic quality certification."}


class ObservationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    build_id: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    check_key: Literal["story_playback","green_screen_playback","caption_revision","library_intake","concurrent_work","access_roles","restore_recovery","reboot_recovery","instagram_post","facebook_post","scheduled_post"]
    result: Literal["pass","fail","not_applicable"]
    note: str = Field(min_length=8,max_length=2000)
    job_id: UUID | None = None
    version: int | None = Field(default=None,ge=1)
    publishing_post_id: UUID | None = None
    observed: bool = False

    @model_validator(mode="after")
    def explicit(self):
        self.note = self.note.strip()
        if len(self.note) < 8 or "\x00" in self.note or not self.observed:
            raise ValueError("confirm an actual observation and describe what you checked")
        spec = SPEC[self.check_key]
        if self.result == "not_applicable" and not spec["allow_na"]:
            raise ValueError("this release check needs a pass or failure")
        if (self.job_id is None) != (self.version is None):
            raise ValueError("include both the job and exact version")
        if self.publishing_post_id is not None and spec["evidence_kind"] != "post":
            raise ValueError("post evidence belongs to a publishing check")
        if self.result == "pass" and spec["evidence_kind"] == "edit" and self.job_id is None:
            raise ValueError("identify the exact job and version you reviewed")
        if self.result == "pass" and spec["evidence_kind"] == "post" and self.publishing_post_id is None:
            raise ValueError("choose the published record you checked on the account")
        return self


@router.post("/acceptance")
def record_observation(payload: ObservationCreate, x_gm_user_login: str | None = Header(default=None)):
    actor = actor_login(x_gm_user_login)
    require_owner(actor)
    settings,now = get_settings(),datetime.now(timezone.utc)
    request = payload.model_dump(mode="json")
    with connection() as database:
        previous = database.execute("SELECT * FROM release_observations WHERE id=%s",(payload.id,)).fetchone()
        if previous:
            if previous["evidence"].get("request") != request or previous["recorded_by"] != actor:
                raise HTTPException(409,"this request already records a different observation")
            return {"id":previous["id"],"recorded":True,"model_calls":0,"posts_created":0}
        if payload.build_id != deployed_build_id(settings):
            raise HTTPException(409,"the deployed build changed; refresh before saving acceptance")
        evidence,run_id = {"version":1,"request":request},None
        if payload.job_id:
            run = database.execute("SELECT * FROM edit_runs WHERE job_id=%s AND version=%s",(payload.job_id,payload.version)).fetchone()
            if not run or (payload.result == "pass" and not preview_available(run,settings.media_root)):
                raise HTTPException(409,"choose an available exact preview for a passing playback check")
            run_id = run["id"]
            manifest = run.get("manifest") or {}
            evidence["edit"] = {"run_id":str(run_id),"version":run["version"],"plan_sha256":manifest.get("edit_plan_sha256")}
            if payload.check_key == "green_screen_playback" and payload.result == "pass":
                direction = manifest.get("creative_direction") if isinstance(manifest.get("creative_direction"),dict) else {}
                composition = direction.get("composition") if isinstance(direction.get("composition"),dict) else {}
                if composition.get("mode") != "green_screen":
                    raise HTTPException(409,"choose a preview created with the green-screen composition mode")
                evidence["composition"] = {
                    key:composition.get(key) for key in (
                        "mode","foreground_asset_id","background_asset_id","chroma_key_color",
                        "chroma_similarity","chroma_blend","spill_suppression",
                    )
                }
            if payload.check_key == "story_playback" and payload.result == "pass":
                final = database.execute("SELECT id,video_path FROM final_exports WHERE edit_run_id=%s AND status='ready' ORDER BY created_at DESC LIMIT 1",(run_id,)).fetchone()
                try:
                    if not final or not run.get("approved_at"):
                        raise ValueError("missing approved final")
                    final_path=resolve_source(settings.media_root,final["video_path"])
                    if not final_path.is_file() or final_path.stat().st_size <= 0:
                        raise ValueError("missing approved final")
                except (OSError,ValueError,TypeError):
                    raise HTTPException(409,"approve and export this version, then download and check the final reel on your phone") from None
                evidence["edit"]["final_export_id"] = str(final["id"])
        if payload.publishing_post_id:
            post = database.execute("SELECT p.id,p.status,p.schedule_requested,p.publish_at,p.approved_revision,c.platform,d.video_sha256 "
                "FROM publishing_posts p JOIN social_connections c ON c.id=p.connection_id JOIN publishing_drafts d ON d.id=p.draft_id WHERE p.id=%s",
                (payload.publishing_post_id,)).fetchone()
            expected = payload.check_key.removesuffix("_post")
            if not post or (expected in ("instagram","facebook") and post["platform"] != expected):
                raise HTTPException(409,"choose a posting record for this platform")
            if payload.result == "pass" and (post["status"] != "published" or (payload.check_key == "scheduled_post" and post["schedule_requested"] is not True)):
                raise HTTPException(409,"a passing post check needs a published result with the requested scheduling evidence")
            evidence["post"] = {key:str(value) if isinstance(value,(UUID,datetime)) else value for key,value in post.items()}
        kind = SPEC[payload.check_key]["evidence_kind"]
        if kind in ("restore","reboot"):
            evidence["recovery"] = recovery(settings,kind,now)
            if payload.result == "pass" and evidence["recovery"]["status"] != "pass":
                raise HTTPException(409,"run the existing recovery verifier; recent passing machine evidence is required")
        evidence["request_hash"] = document_sha256(request)
        inserted = database.execute("""INSERT INTO release_observations(id,build_id,check_key,result,note,job_id,edit_run_id,publishing_post_id,evidence,recorded_by)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING RETURNING id""",
            (payload.id,payload.build_id,payload.check_key,payload.result,payload.note,payload.job_id,run_id,payload.publishing_post_id,Jsonb(evidence),actor)).fetchone()
        if not inserted:
            raise HTTPException(409,"this observation was saved concurrently; refresh before retrying")
    return {"id":payload.id,"recorded":True,"model_calls":0,"posts_created":0}
