"""Read-only pilot contract: one trusted studio, not public multi-tenancy."""

from fastapi import APIRouter
from app.config import get_settings
from app.database import connection

router = APIRouter(prefix="/api/v1", tags=["pilot readiness"])


@router.get("/pilot-readiness")
def pilot_readiness():
    settings = get_settings()
    with connection() as database:
        tables = list(
            database.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('source_products','asset_range_annotations','learning_lessons','learning_evaluations')"
            ).fetchall()
        )
        members = list(
            database.execute(
                "SELECT role,count(*) AS count FROM studio_members WHERE active=true GROUP BY role"
            ).fetchall()
        )
        failures = database.execute(
            "SELECT count(*) AS count FROM edit_runs WHERE status='failed' AND created_at>now()-interval '7 days'"
        ).fetchone()
    schema_ready = len(tables) == 4
    return {
        "version": "19-25.1",
        "schema_ready": schema_ready,
        "configured_private_owner": bool(settings.tailscale_owner_login),
        "member_roles": {row["role"]: row["count"] for row in members},
        "failed_previews_last_7_days": failures["count"],
        "deployment_scope": "one shared private studio; members can see the shared library",
        "public_multi_tenant_ready": False,
        "tools": {
            "precise_trim_split": True,
            "local_camera_keyframes": True,
            "phrase_voice_gain": True,
            "caption_windows": True,
            "picture_layers": True,
            "chroma_key": True,
            "silent_layer_retiming_freeze": True,
            "ai_segmentation": False,
            "automatic_tracking": False,
            "independent_dialogue_joins": True,
        },
        "learning": {
            "explicit_trials_only": True,
            "held_out_source_hashes": True,
            "promotion_requires_playback": True,
            "rollback": True,
            "automatic_model_training": False,
        },
        "remaining_acceptance": [
            "deploy and run the live suite",
            "compare real HDR footage and listen on a phone",
            "test one editor and one viewer through private access",
            "verify current USB/off-site backup and isolated restore",
            "review library import, concept selection, local edits and export with a new tester",
        ],
        "hosted_model_calls": 0,
    }
