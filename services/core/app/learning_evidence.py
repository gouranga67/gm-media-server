"""Local comparison provenance and conservative source-independent scoring."""

import re
from pathlib import Path

from fastapi import HTTPException
from app.edit_plan import document_sha256
from app.media_analysis import resolve_source
from app.revision_report import compare_revision

HASH = re.compile(r"^[0-9a-f]{64}$")


def known_hashes(values):
    return bool(values) and all(isinstance(value, str) and HASH.fullmatch(value) for value in values)


def preview_available(run, media_root: Path):
    if run.get("status") != "ready" or not run.get("preview_path"):
        return False
    try:
        path = resolve_source(media_root, run["preview_path"])
        return path.is_file() and path.stat().st_size > 0
    except (OSError, ValueError):
        return False


USAGE_SQL = """SELECT edit_run_id,count(*) AS requests,sum(total_tokens) AS total_tokens,
    sum(latency_ms) AS model_latency_ms FROM ai_usage_events
    WHERE edit_run_id=ANY(%s::uuid[]) GROUP BY edit_run_id"""


def usage_for_runs(database, ids):
    if not ids:
        return {}
    return {str(row["edit_run_id"]): {"requests": int(row["requests"]),
        "total_tokens": int(row["total_tokens"]), "model_latency_ms": int(row["model_latency_ms"])}
        for row in database.execute(USAGE_SQL, (list(ids),)).fetchall()}


def comparison_evidence(database, item, baseline, candidate, media_root):
    from app.learning_lab import source_hashes
    if not preview_available(baseline, media_root) or not preview_available(candidate, media_root):
        raise HTTPException(409, "both exact preview files must be available for playback before scoring")
    if baseline.get("evaluation_lesson_id"):
        raise HTTPException(409, "use an ordinary edit as the baseline, not another lesson trial")
    documents = {}
    for run in (baseline, candidate):
        row = database.execute("SELECT document FROM edit_plans WHERE id=%s", (run["edit_plan_id"],)).fetchone()
        if not row:
            raise HTTPException(409, "a compared edit plan is unavailable")
        documents[str(run["id"])] = row["document"]
    # Exclude all attached footage, including unused alternatives: this is more
    # conservative than claiming independence from the two selected cuts alone.
    hashes = source_hashes(database, [str(candidate["job_id"])])
    if not known_hashes(hashes):
        raise HTTPException(409, "all comparison footage needs known checksums before scoring")
    usage = usage_for_runs(database, [baseline["id"], candidate["id"]])
    old, new = documents[str(baseline["id"])], documents[str(candidate["id"])]
    for run, document in ((baseline,old),(candidate,new)):
        manifest = run.get("manifest") or {}
        rendered_hashes = [source.get("sha256") for source in manifest.get("sources",[])]
        if (manifest.get("edit_plan_sha256") != document_sha256(document)
                or not known_hashes(rendered_hashes) or not set(rendered_hashes) <= set(hashes)):
            raise HTTPException(409,"the rendered plan/source provenance is incomplete or changed; re-render before comparing")
    return {"version": 1, "source_hashes": sorted(set(hashes)),
        "baseline_run_id": str(baseline["id"]), "candidate_run_id": str(candidate["id"]),
        "baseline_plan_id": str(baseline["edit_plan_id"]), "candidate_plan_id": str(candidate["edit_plan_id"]),
        "baseline_plan_hash": document_sha256(old), "candidate_plan_hash": document_sha256(new),
        "directive_hash": document_sha256({"directive": item["directive"]}),
        "executable_changed": bool(compare_revision(old, new)["changed"]),
        "baseline_usage": usage.get(str(baseline["id"])), "candidate_usage": usage.get(str(candidate["id"])),
        "baseline_quality": (baseline.get("manifest") or {}).get("quality_review", {}).get("status", "not_recorded"),
        "candidate_quality": (candidate.get("manifest") or {}).get("quality_review", {}).get("status", "not_recorded"),
    }


def evaluation_result(rows, *, item=None):
    eligible, excluded = [], 0
    for row in rows:
        evidence = row.get("evidence") or {}
        valid = (evidence.get("version") == 1 and known_hashes(evidence.get("source_hashes"))
            and all(HASH.fullmatch(str(evidence.get(key, ""))) for key in ("baseline_plan_hash", "candidate_plan_hash"))
            and all(str(row.get(key)) == evidence.get(key) for key in ("baseline_run_id", "candidate_run_id"))
            and isinstance(evidence.get("executable_changed"), bool))
        if item:
            valid = valid and str(row["job_id"]) not in item["training_job_ids"]
            valid = valid and not set(evidence.get("source_hashes") or []) & set(item["training_source_hashes"])
            valid = valid and evidence.get("directive_hash") == document_sha256({"directive": item["directive"]})
        if valid:
            eligible.append(row)
        else:
            excluded += 1
    # Connected source overlap counts once, even through an intermediate job.
    groups = []
    for row in eligible:
        hashes, jobs = set(row["evidence"]["source_hashes"]), {str(row["job_id"])}
        members = [row]
        remaining = []
        for old_hashes, old_jobs, old_members in groups:
            if hashes & old_hashes or jobs & old_jobs:
                hashes |= old_hashes
                jobs |= old_jobs
                members += old_members
            else:
                remaining.append((old_hashes, old_jobs, old_members))
        # A newly merged component can connect an earlier disjoint component.
        while True:
            linked = [group for group in remaining if hashes & group[0] or jobs & group[1]]
            if not linked:
                break
            remaining = [group for group in remaining if group not in linked]
            for old_hashes, old_jobs, old_members in linked:
                hashes |= old_hashes; jobs |= old_jobs; members += old_members
        groups = [*remaining, (hashes, jobs, members)]
    def delta(row):
        value = int(row["candidate_rating"]) - int(row["baseline_rating"])
        return value if row["evidence"].get("executable_changed") else min(0, value)
    deltas = [min(delta(row) for row in members) for _, _, members in groups]
    # Missing/old provenance cannot add positive evidence. A recorded lower
    # rating still blocks promotion until its comparison is reviewed again.
    regressions = sum(int(row["candidate_rating"]) < int(row["baseline_rating"]) for row in rows)
    measured = [row["evidence"] for row in eligible
        if row["evidence"].get("baseline_usage") and row["evidence"].get("candidate_usage")]
    return {"held_out_jobs": len(groups), "rated_jobs": len({str(row["job_id"]) for row in rows}),
        "excluded_comparisons": excluded, "overlapping_comparisons": len(eligible) - len(groups),
        "rating_delta": round(sum(deltas) / len(deltas), 2) if deltas else None,
        "regressions": regressions, "can_promote": len(groups) >= 3 and not regressions and sum(deltas) > 0,
        "token_delta": round(sum(e["candidate_usage"]["total_tokens"] - e["baseline_usage"]["total_tokens"] for e in measured) / len(measured)) if measured else None,
        "costed_comparisons": len(measured), "method": "human paired playback; source-independent groups; saved plan provenance",
        "note": "Three independent footage groups, no lower ratings and one executable improvement are required. Shared footage counts once at its lowest delta. Legacy scores need a saved comparison snapshot. Ratings are subjective; trials do not prove causality or universal quality.",
    }
