"""Durable, bounded local music analysis. No hosted model requests."""

from typing import Any

from psycopg.types.json import Jsonb

from app.config import get_settings
from app.database import connection
from app.media_analysis import resolve_source
from app.music_analysis import MUSIC_ANALYSIS_VERSION, analyze_music_beats


def process_one_music_track(state: Any) -> bool:
    settings = get_settings()
    timeout = min(settings.analysis_command_timeout_seconds, 120)
    with connection() as database:
        # An interrupted final attempt must become visible as failed rather
        # than remaining 'running' forever. Earlier attempts can be reclaimed.
        database.execute("""
            UPDATE music_tracks SET beat_analysis_status = 'failed',
                beat_analysis_error = 'Music analysis lease expired after the final attempt.',
                beat_analysis_lease_expires_at = NULL, updated_at = now()
            WHERE beat_analysis_status = 'running'
              AND beat_analysis_lease_expires_at <= now() AND beat_analysis_attempts >= 3
        """)
        row = database.execute("""
            WITH candidate AS (
                SELECT id FROM music_tracks
                WHERE active = true AND (
                    beat_analysis_status = 'pending'
                    OR (beat_analysis_status = 'ready' AND beat_analysis_version < %s)
                    OR (beat_analysis_status = 'failed' AND beat_analysis_attempts < 3
                        AND beat_analysis_next_attempt_at <= now())
                    OR (beat_analysis_status = 'running' AND beat_analysis_attempts < 3
                        AND beat_analysis_lease_expires_at <= now())
                )
                ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED
            )
            UPDATE music_tracks AS track
            SET beat_analysis_status = 'running',
                beat_analysis_attempts = CASE WHEN track.beat_analysis_version < %s
                    AND track.beat_analysis_status = 'ready' THEN 1
                    ELSE track.beat_analysis_attempts + 1 END,
                beat_analysis_lease_expires_at = now() + (%s * interval '1 second'),
                beat_analysis_error = NULL, updated_at = now()
            FROM candidate WHERE track.id = candidate.id
            RETURNING track.id, track.storage_key, track.duration_seconds, track.beat_analysis_attempts
        """, (MUSIC_ANALYSIS_VERSION, MUSIC_ANALYSIS_VERSION, timeout + 120)).fetchone()
    if row is None:
        return False

    state.active_music_track_id = str(row["id"])
    try:
        source = resolve_source(settings.media_root, str(row["storage_key"]))
        analysis = analyze_music_beats(source, float(row["duration_seconds"]), timeout)
        with connection() as database:
            completed = database.execute("""
                UPDATE music_tracks SET bpm = %s, beat_grid_seconds = %s,
                    beat_analysis_status = 'ready', beat_analysis_version = %s,
                    beat_analysis_lease_expires_at = NULL, beat_analysis_next_attempt_at = NULL,
                    beat_analysis_error = NULL, updated_at = now()
                WHERE id = %s AND beat_analysis_status = 'running' AND beat_analysis_attempts = %s
                  AND beat_analysis_lease_expires_at > now()
            """, (analysis["bpm"], Jsonb(analysis["beat_grid_seconds"]), MUSIC_ANALYSIS_VERSION,
                  row["id"], row["beat_analysis_attempts"])).rowcount == 1
        if completed:
            print(f"music beat analysis ready: {row['id']}", flush=True)
        else:
            print(f"music beat analysis lease expired or superseded: {row['id']}", flush=True)
    except Exception as error:
        with connection() as database:
            database.execute("""
                UPDATE music_tracks SET beat_analysis_status = 'failed', beat_analysis_error = %s,
                    beat_analysis_lease_expires_at = NULL,
                    beat_analysis_next_attempt_at = now() + (%s * interval '1 minute'),
                    updated_at = now()
                WHERE id = %s AND beat_analysis_status = 'running' AND beat_analysis_attempts = %s
                  AND beat_analysis_lease_expires_at > now()
            """, (str(error)[:500], 5 * row["beat_analysis_attempts"], row["id"], row["beat_analysis_attempts"]))
        print(f"music beat analysis deferred: {row['id']}", flush=True)
    finally:
        state.active_music_track_id = None
    return True
