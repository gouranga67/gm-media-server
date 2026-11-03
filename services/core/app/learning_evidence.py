"""Local comparison provenance and conservative source-independent scoring."""

import re
from pathlib import Path

from fastapi import HTTPException
from app.edit_plan import document_sha256
from app.media_analysis import resolve_source
from app.revision_report import compare_revision

HASH = re.compile(r"^[0-9a-f]{64}$")
RUBRIC_KEYS = ("brief", "story", "speech", "captions", "visuals", "audio")
RUBRIC_VALUES = {"better", "same", "worse", "not_applicable"}
LOCAL_PROVIDERS = {"local_revision_instruction","local_finishing","local_timeline","local_caption_layout",
    "local_effect_controls","local_broll_controls","local_caption","local_subtitles"}


def usage_snapshot(run, recorded):
    if recorded is not None:
        return recorded
    if run.get("provider") in LOCAL_PROVIDERS:
        return {"requests":0,"total_tokens":0,"model_latency_ms":0,"measurement":"recorded_local_execution"}
    return None


def measured_usage(value):
    return isinstance(value, dict) and all(isinstance(value.get(key), int) and not isinstance(value[key], bool)
        and value[key] >= 0 for key in ("requests", "total_tokens", "model_latency_ms"))


def attention_codes(run):
    report = (run.get("manifest") or {}).get("quality_review") or {}
    return {str(check["code"]) for check in report.get("checks", [])
        if isinstance(check, dict) and check.get("code") and check.get("status") in ("attention", "failed")}


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


def comparison_evidence(database, item, baseline, candidate, media_root, *, case=None, rubric=None, reviewed_both=False):
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
    evidence = {"version": 1, "source_hashes": sorted(set(hashes)),
        "baseline_run_id": str(baseline["id"]), "candidate_run_id": str(candidate["id"]),
        "baseline_plan_id": str(baseline["edit_plan_id"]), "candidate_plan_id": str(candidate["edit_plan_id"]),
        "baseline_plan_hash": document_sha256(old), "candidate_plan_hash": document_sha256(new),
        "directive_hash": document_sha256({"directive": item["directive"]}),
        "executable_changed": bool(compare_revision(old, new)["changed"]),
        "baseline_usage": usage_snapshot(baseline,usage.get(str(baseline["id"]))),
        "candidate_usage": usage_snapshot(candidate,usage.get(str(candidate["id"]))),
        "baseline_quality": (baseline.get("manifest") or {}).get("quality_review", {}).get("status", "not_recorded"),
        "candidate_quality": (candidate.get("manifest") or {}).get("quality_review", {}).get("status", "not_recorded"),
    }
    if case is not None:
        evidence.update(version=2, case_id=str(case["id"]), case_snapshot_hash=case["snapshot_hash"],
            recording_group=" ".join(case["recording_group"].split()).casefold(),
            criteria_hash=document_sha256({"expectations": case["expectations"], "category": case["category"],
                "recording_group":case["recording_group"],"max_candidate_tokens": case["max_candidate_tokens"]}),
            max_candidate_tokens=case["max_candidate_tokens"], rubric=rubric, reviewed_both=reviewed_both,
            baseline_model=baseline.get("model"), candidate_model=candidate.get("model"),
            new_quality_findings=sorted(attention_codes(candidate) - attention_codes(baseline)))
    return evidence


def evaluation_result(rows, *, item=None):
    eligible, excluded = [], 0
    for row in rows:
        evidence = row.get("evidence") or {}
        valid = (evidence.get("version") in (1, 2) and known_hashes(evidence.get("source_hashes"))
            and all(HASH.fullmatch(str(evidence.get(key, ""))) for key in ("baseline_plan_hash", "candidate_plan_hash"))
            and all(str(row.get(key)) == evidence.get(key) for key in ("baseline_run_id", "candidate_run_id"))
            and isinstance(evidence.get("executable_changed"), bool))
        if item:
            valid = valid and str(row["job_id"]) not in item["training_job_ids"]
            valid = valid and not set(evidence.get("source_hashes") or []) & set(item["training_source_hashes"])
            valid = valid and evidence.get("directive_hash") == document_sha256({"directive": item["directive"]})
        if evidence.get("version") == 2:
            rubric = evidence.get("rubric") or {}
            valid = valid and isinstance(rubric, dict) and evidence.get("reviewed_both") is True and set(rubric) == set(RUBRIC_KEYS)
            valid = valid and all(isinstance(value,str) and value in RUBRIC_VALUES for value in rubric.values())
            valid = valid and bool(evidence.get("case_id")) and bool(HASH.fullmatch(str(evidence.get("case_snapshot_hash", ""))))
            valid = valid and isinstance(evidence.get("recording_group"),str) and bool(evidence["recording_group"].strip())
            valid = valid and bool(HASH.fullmatch(str(evidence.get("criteria_hash", ""))))
        if item and item.get("evaluation_protocol", 1) >= 2:
            valid = valid and evidence.get("version") == 2
        if valid:
            eligible.append(row)
        else:
            excluded += 1
    # Connected source overlap counts once, even through an intermediate job.
    groups = []
    for row in eligible:
        hashes, jobs = set(row["evidence"]["source_hashes"]), {str(row["job_id"])}
        if row["evidence"].get("version") == 2:
            jobs.add("recording:" + " ".join(row["evidence"]["recording_group"].split()).casefold())
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
        evidence = row["evidence"]
        improvement = evidence.get("version") != 2 or "better" in (evidence.get("rubric") or {}).values()
        return value if evidence.get("executable_changed") and improvement else min(0, value)
    deltas = [min(delta(row) for row in members) for _, _, members in groups]
    # Missing/old provenance cannot add positive evidence. A recorded lower
    # rating still blocks promotion until its comparison is reviewed again.
    cohort = [row for row in rows if (row.get("evidence") or {}).get("version") == 2] if item and item.get("evaluation_protocol",1) >= 2 else rows
    regressions = sum(int(row["candidate_rating"]) < int(row["baseline_rating"]) for row in cohort)
    measured = [row["evidence"] for row in eligible
        if row["evidence"].get("baseline_usage") and row["evidence"].get("candidate_usage")]
    strict = [row["evidence"] for row in eligible if row["evidence"].get("version") == 2]
    rubric_regressions = sum("worse" in rubric.values() for row in cohort
        for rubric in [(row.get("evidence") or {}).get("rubric")] if isinstance(rubric,dict))
    unmeasured = sum(not measured_usage(e.get("baseline_usage")) or not measured_usage(e.get("candidate_usage")) for e in strict)
    expensive = sum(e.get("max_candidate_tokens") is not None and measured_usage(e.get("candidate_usage"))
        and e["candidate_usage"]["total_tokens"] > e["max_candidate_tokens"] for e in strict)
    technical = sum(bool(e.get("new_quality_findings")) for e in strict)
    blockers = []
    if len(groups) < 3: blockers.append("Review three independent footage groups.")
    if regressions or rubric_regressions: blockers.append("Resolve the recorded overall or checklist regressions.")
    if not deltas or sum(deltas) <= 0: blockers.append("Record a preference for a changed edit with a specific checklist improvement.")
    if unmeasured: blockers.append("Some saved-case pairs lack measured model usage; missing usage is not zero cost.")
    if expensive: blockers.append("A trial exceeded its test case's token qualification ceiling.")
    if technical: blockers.append("A trial introduced new local technical warnings; inspect those exact previews.")
    return {"held_out_jobs": len(groups), "rated_jobs": len({str(row["job_id"]) for row in rows}),
        "excluded_comparisons": excluded, "overlapping_comparisons": len(eligible) - len(groups),
        "rating_delta": round(sum(deltas) / len(deltas), 2) if deltas else None,
        "regressions": regressions, "can_promote": not blockers,
        "rubric_regressions": rubric_regressions, "unmeasured_pairs": unmeasured,
        "budget_exceeded_pairs": expensive, "technical_regressions": technical, "blockers": blockers,
        "token_delta": round(sum(e["candidate_usage"]["total_tokens"] - e["baseline_usage"]["total_tokens"] for e in measured) / len(measured)) if measured else None,
        "costed_comparisons": len(measured), "method": "human paired playback; source-independent groups; saved plan provenance",
        "note": "Three independent footage groups, no lower ratings and one executable improvement are required. Shared footage counts once at its lowest delta. Legacy scores need a saved comparison snapshot. Ratings are subjective; trials do not prove causality or universal quality.",
    }


def with_trial_readiness(report, item, trials, evaluations):
    """Do not promote a new protocol lesson while other ready pairs go unreviewed."""
    if item.get("evaluation_protocol",1) < 2:
        return report
    scored = {str(row["candidate_run_id"]) for row in evaluations}
    current = [trial for trial in trials if trial.get("evaluation_case_id")]
    active = sum(trial.get("status") in ("pending","planning","rendering") for trial in current)
    unreviewed = sum(trial.get("status") == "ready" and str(trial["id"]) not in scored for trial in current)
    failed = sum(trial.get("status") == "failed" for trial in trials)
    blockers = list(report["blockers"])
    if active: blockers.append("Wait for every queued trial to finish.")
    if unreviewed: blockers.append("Review every finished trial pair; do not select only the favourites.")
    return {**report,"active_trials":active,"unreviewed_trials":unreviewed,"failed_trials":failed,"legacy_trials":len(trials)-len(current),
        "blockers":blockers,"can_promote":not blockers}
