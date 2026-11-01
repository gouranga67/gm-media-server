-- Beat analysis is optional local background work, independent of playback
-- eligibility. Preserve previously computed grids and do not reprocess them.
ALTER TABLE music_tracks
    ADD COLUMN beat_analysis_status text NOT NULL DEFAULT 'pending'
        CHECK (beat_analysis_status IN ('pending', 'running', 'ready', 'failed')),
    ADD COLUMN beat_analysis_version integer NOT NULL DEFAULT 0,
    ADD COLUMN beat_analysis_attempts integer NOT NULL DEFAULT 0
        CHECK (beat_analysis_attempts >= 0),
    ADD COLUMN beat_analysis_lease_expires_at timestamptz,
    ADD COLUMN beat_analysis_next_attempt_at timestamptz,
    ADD COLUMN beat_analysis_error text;

UPDATE music_tracks
SET beat_analysis_status = 'ready', beat_analysis_version = 1
WHERE bpm IS NOT NULL AND jsonb_array_length(beat_grid_seconds) > 0;

CREATE INDEX music_tracks_beat_analysis_pending_idx
    ON music_tracks(created_at)
    WHERE active = true AND beat_analysis_status IN ('pending', 'running', 'failed');
