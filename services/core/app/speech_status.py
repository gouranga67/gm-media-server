"""Read-only local alignment progress; never loads a model in the API."""

from app.speech_precision import VERSION, profile


def speech_precision_status(settings, connect):
    with connect() as database:
        rows = database.execute(
            """SELECT i.manifest #>> '{derived,speech_precision_profile}' AS profile,
                      i.manifest #> '{derived,speech_precision_summary}' AS summary
               FROM assets a JOIN asset_ingests i ON i.asset_id=a.id
               WHERE a.status='ready' AND i.status='ready' AND a.library_status='active'
                 AND i.manifest #>> '{derived,transcript}' IS NOT NULL"""
        ).fetchall()
    current = [r for r in rows if r.get("profile") == profile(settings)]
    counts = {name: sum(int((r.get("summary") or {}).get(name) or 0) for r in current)
              for name in ("total_words", "aligned_words", "uncertain_words", "interpolated_words")}
    enabled = settings.speech_alignment_enabled
    return {"version": VERSION, "enabled": enabled,
            "status": "disabled" if not enabled else "empty" if not rows else "ready" if len(current) == len(rows) else "backfilling",
            "ready_sources": len(rows), "processed_sources": len(current), "pending_sources": len(rows) - len(current),
            "source_statuses": {name: sum((r.get("summary") or {}).get("status") == name for r in current)
                                for name in ("aligned", "partial", "estimated", "unsupported_language", "unavailable")},
            **counts, "read_only": True, "hosted_model_calls": 0,
            "note": "Counts describe analysis coverage, not measured timing accuracy. New jobs use cached timing; saved plans keep their own snapshots."}
