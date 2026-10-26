"""Durable library discovery followed by explicit, idempotent concept selection."""
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, status
from psycopg.types.json import Jsonb

from app.concept_inventory import concept_brief, load_inventory, validate_concepts
from app.concept_provider import generate_concepts
from app.concept_schemas import ConceptRequestCreate, ConceptSelection
from app.config import get_settings
from app.database import connection
from app.productization import actor_login, assert_ai_budget, assert_job_capacity

router = APIRouter(prefix="/api/v1/concepts", tags=["concepts"])


def _public(row: dict, jobs: list[dict] | None = None) -> dict:
    return {key: value for key, value in {**row, "jobs": jobs or []}.items() if key != "inventory"}


@router.get("/library-status")
def concept_library_status() -> dict:
    with connection() as database:
        row = database.execute("""
            SELECT count(DISTINCT a.sha256) FILTER (WHERE a.status='ready')::integer AS unique_sources,
                   count(DISTINCT a.sha256) FILTER (WHERE c.status='ready')::integer AS catalogued_sources,
                   count(DISTINCT a.sha256) FILTER (WHERE c.status='ready' AND EXISTS (
                       SELECT 1 FROM asset_catalog_segments s WHERE s.asset_id=a.id AND s.segment_kind='transcript'
                   ) AND a.mime_type LIKE 'video/%%')::integer AS spoken_sources,
                   count(DISTINCT a.sha256) FILTER (WHERE v.status IN ('ready','aliased'))::integer AS visually_indexed_sources,
                   count(*) FILTER (WHERE a.status<>'failed' AND c.status IS DISTINCT FROM 'failed' AND (a.status<>'ready' OR c.status IS DISTINCT FROM 'ready'))::integer AS still_processing,
                   count(*) FILTER (WHERE a.status='failed' OR c.status='failed')::integer AS analysis_failed
            FROM assets a LEFT JOIN asset_catalogs c ON c.asset_id=a.id
            LEFT JOIN asset_visual_indexes v ON v.asset_id=a.id
            WHERE a.library_status='active'
        """).fetchone()
    return row or {}


@router.get("")
def list_concept_requests() -> list[dict]:
    with connection() as database:
        rows = database.execute("SELECT * FROM reel_concept_requests ORDER BY created_at DESC LIMIT 20").fetchall()
    return [_public(row) for row in rows]


@router.get("/{request_id}")
def get_concept_request(request_id: UUID) -> dict:
    with connection() as database:
        row = database.execute("SELECT * FROM reel_concept_requests WHERE id=%s", (request_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="concept session not found")
        jobs = database.execute("SELECT concept_id,job_id FROM reel_concept_jobs WHERE request_id=%s ORDER BY created_at", (request_id,)).fetchall()
    return _public(row, list(jobs))


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def request_concepts(payload: ConceptRequestCreate) -> dict:
    with connection() as database:
        database.execute("SELECT pg_advisory_xact_lock(hashtext('gm:concept-request'))")
        existing = database.execute("SELECT * FROM reel_concept_requests WHERE id=%s", (payload.id,)).fetchone()
        if existing is not None:
            if any(str(existing.get(key, "story" if key == "reel_kind" else None) or "") != str(value or "") for key, value in payload.model_dump().items() if key != "id"):
                raise HTTPException(status_code=409, detail="this concept request ID belongs to different settings")
            return _public(existing)
        pending = database.execute("SELECT count(*) AS count FROM reel_concept_requests WHERE status IN ('pending','generating')").fetchone()
        if int(pending["count"]) >= 2:
            raise HTTPException(status_code=429, detail="two concept requests are already queued; wait for them to finish")
        assert_ai_budget(database)
        inventory, coverage = load_inventory(database, payload)
        if payload.reel_kind == "bloopers" and not any(item.get("blooper_candidate") for item in inventory["evidence"]):
            raise HTTPException(status_code=409, detail="No possible bloopers were found in the scanned transcripts. No model request was queued. Try another collection or add footage with recorded mistakes, retakes or laughter; purely visual bloopers need manual review.")
        if payload.reel_kind == "story" and len(inventory["evidence"]) < 2:
            raise HTTPException(status_code=409, detail="not enough indexed spoken video is ready in this scope; wait for analysis, choose a broader collection, or add talking footage")
        row = database.execute("""
            INSERT INTO reel_concept_requests (id,focus,audience,collection_id,privacy_mode,inventory,coverage,reel_kind)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """, (payload.id, payload.focus, payload.audience, payload.collection_id, payload.privacy_mode, Jsonb(inventory), Jsonb(coverage), payload.reel_kind)).fetchone()
    return _public(row)


def _record_usage(database: Any, request_id: UUID, provenance: dict) -> None:
    usage = provenance.get("usage") or {}
    database.execute("""
        INSERT INTO ai_usage_events (concept_request_id,provider,model,reasoning_effort,request_kind,response_id,
            input_tokens,cached_input_tokens,output_tokens,reasoning_tokens,total_tokens,latency_ms)
        VALUES (%s,%s,%s,'medium','concepts',%s,%s,%s,%s,%s,%s,%s)
    """, (request_id, provenance["provider"], provenance["model"], usage.get("response_id"),
          int(usage.get("input_tokens") or 0), int(usage.get("cached_input_tokens") or 0),
          int(usage.get("output_tokens") or 0), int(usage.get("reasoning_tokens") or 0),
          int(usage.get("total_tokens") or 0), int(usage.get("latency_ms") or 0)))
    database.execute("UPDATE reel_concept_requests SET total_tokens=%s,model=%s,updated_at=now() WHERE id=%s",
                     (int(usage.get("total_tokens") or 0), provenance["model"], request_id))


def recover_interrupted_concepts() -> int:
    # Never auto-respend a model request after a crash or an ambiguous timeout.
    with connection() as database:
        result = database.execute("""UPDATE reel_concept_requests SET status='failed',
            error='Concept generation was interrupted. It was not automatically retried; generate again only if you want another request.',
            lease_expires_at=NULL,updated_at=now() WHERE status='generating' AND lease_expires_at<now()""")
    return result.rowcount


def process_one_concept(state: Any) -> bool:
    settings = get_settings()
    with connection() as database:
        row = database.execute("""SELECT * FROM reel_concept_requests WHERE status='pending'
            ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED""").fetchone()
        if row is None:
            return False
        database.execute("UPDATE reel_concept_requests SET status='generating',lease_expires_at=now()+(%s*interval '1 second'),updated_at=now() WHERE id=%s",
                         (settings.edit_lease_seconds, row["id"]))
    state.active_concept_request_id = str(row["id"])
    try:
        assert_ai_budget()
        document, provenance = generate_concepts(row["inventory"], row["privacy_mode"], settings)
        # Persist measured usage even when the returned proposal fails evidence validation.
        with connection() as database:
            _record_usage(database, row["id"], provenance)
        concepts = validate_concepts(document, row["inventory"], row["id"])
        for concept in concepts:
            concept_brief(concept)
        with connection() as database:
            database.execute("UPDATE reel_concept_requests SET status='ready',concepts=%s,error=NULL,lease_expires_at=NULL,updated_at=now() WHERE id=%s",
                             (Jsonb(concepts), row["id"]))
    except Exception as error:
        with connection() as database:
            database.execute("UPDATE reel_concept_requests SET status='failed',error=%s,lease_expires_at=NULL,updated_at=now() WHERE id=%s",
                             (str(error)[:1200], row["id"]))
        print(f"concept request failed: {row['id']}: {error}", flush=True)
    finally:
        state.active_concept_request_id = None
    return True


@router.post("/{request_id}/render", status_code=status.HTTP_202_ACCEPTED)
def render_selected_concepts(request_id: UUID, payload: ConceptSelection, x_gm_user_login: str | None = Header(default=None)) -> dict:
    with connection() as database:
        session = database.execute("SELECT * FROM reel_concept_requests WHERE id=%s FOR UPDATE", (request_id,)).fetchone()
        if session is None or session["status"] != "ready":
            raise HTTPException(status_code=409, detail="wait for ready concept options before creating previews")
        options = {item["id"]: item for item in session["concepts"]}
        if any(str(id) not in options for id in payload.concept_ids):
            raise HTTPException(status_code=422, detail="select only concepts from this session")
        existing = database.execute("SELECT concept_id,job_id FROM reel_concept_jobs WHERE request_id=%s", (request_id,)).fetchall()
        jobs = {str(item["concept_id"]): item["job_id"] for item in existing}
        wanted = [options[str(id)] for id in payload.concept_ids if str(id) not in jobs]
        if wanted:
            assert_ai_budget(database)
            asset_ids = list(dict.fromkeys(id for concept in wanted for id in concept["asset_ids"]))
            available = database.execute("""SELECT a.id,a.sha256 FROM assets a JOIN asset_ingests i ON i.asset_id=a.id
                WHERE a.id=ANY(%s) AND a.status='ready' AND a.library_status='active' AND i.status='ready'
                ORDER BY a.id FOR SHARE OF a""", ([UUID(id) for id in asset_ids],)).fetchall()
            hashes = {str(row["id"]): row["sha256"] for row in available}
            inventory = {asset["asset_id"]: asset for asset in session["inventory"]["assets"]}
            if any(id not in hashes or hashes[id] != inventory[id]["sha256"] for id in asset_ids):
                raise HTTPException(status_code=409, detail="some concept footage is no longer active; restore it from Trash or generate fresh ideas")
            if payload.music_mode.value != "none":
                compatible = database.execute("""SELECT 1 FROM music_tracks WHERE active=true AND commercial_use=true AND synthetic_media=false
                    AND ('all_social'=ANY(allowed_platforms) OR %s=ANY(allowed_platforms)) LIMIT 1""", (payload.target_platform.value,)).fetchone()
                if compatible is None:
                    raise HTTPException(status_code=422, detail="no approved music is available for this platform; choose no music")
        for concept in wanted:
            project_id, job_id = uuid4(), uuid4()
            assert_job_capacity(database, job_id)
            database.execute("INSERT INTO projects (id,name,brief,privacy_mode,ai_copy_allowed) VALUES (%s,%s,%s,%s,false)",
                             (project_id, concept["title"], concept_brief(concept), session["privacy_mode"]))
            target = next((value for value in (20,30,45,60) if value >= concept["estimated_seconds"]), 60)
            database.execute("""INSERT INTO jobs (id,project_id,recipe,status,target_duration_seconds,edit_style,
                music_mode,effect_level,target_platform,story_goal,audience,editor_model,reasoning_effort,output_aspect,created_by_login)
                VALUES (%s,%s,'talking_head','planning',%s,'high_impact',%s,%s,%s,%s,%s,%s,'medium','vertical',%s)""",
                             (job_id, project_id, target, payload.music_mode.value, payload.effect_level.value,
                              payload.target_platform.value, concept["angle"][:1200], session["audience"], get_settings().chatgpt_model, actor_login(x_gm_user_login)))
            for asset_id in concept["asset_ids"]:
                database.execute("INSERT INTO job_assets (job_id,asset_id) VALUES (%s,%s)", (job_id, UUID(asset_id)))
            database.execute("INSERT INTO edit_runs (job_id,version) VALUES (%s,1)", (job_id,))
            database.execute("INSERT INTO reel_concept_jobs (request_id,concept_id,job_id) VALUES (%s,%s,%s)", (request_id, UUID(concept["id"]), job_id))
            database.execute("INSERT INTO job_events (job_id,event_type,payload) VALUES (%s,'library_concept_selected',%s)",
                             (job_id, Jsonb({"concept_request_id": str(request_id), "concept_id": concept["id"], "preview_requested": True})))
            jobs[concept["id"]] = job_id
    return {"jobs": [{"concept_id": str(id), "job_id": str(jobs[str(id)])} for id in payload.concept_ids]}
