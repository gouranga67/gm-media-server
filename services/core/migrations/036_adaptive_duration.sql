ALTER TABLE jobs
    ADD COLUMN duration_mode text NOT NULL DEFAULT 'aim' CHECK (duration_mode IN ('follow_story','aim','strict')),
    ADD COLUMN max_duration_seconds integer NOT NULL DEFAULT 90 CHECK (max_duration_seconds BETWEEN 5 AND 120);
-- Keep the existing preference for old jobs, with a small flexible allowance.
-- New jobs follow the story unless an explicit limit is chosen.
ALTER TABLE jobs ALTER COLUMN duration_mode SET DEFAULT 'follow_story';
ALTER TABLE edit_runs ADD COLUMN duration_policy jsonb;
UPDATE edit_runs r SET duration_policy=jsonb_build_object(
    'duration_mode',j.duration_mode,'max_duration_seconds',j.max_duration_seconds,
    'target_duration_seconds',coalesce(j.target_duration_seconds,45))
FROM jobs j WHERE j.id=r.job_id;
ALTER TABLE edit_feedback DROP CONSTRAINT edit_feedback_time_range;
ALTER TABLE edit_feedback ADD CONSTRAINT edit_feedback_time_range CHECK (
    (start_seconds IS NULL AND end_seconds IS NULL) OR
    (start_seconds IS NOT NULL AND end_seconds IS NOT NULL AND start_seconds >= 0 AND end_seconds > start_seconds AND end_seconds <= 120)
);
