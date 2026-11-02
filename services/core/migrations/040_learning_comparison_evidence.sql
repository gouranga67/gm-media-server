-- Existing scores remain visible, but need a recorded comparison snapshot
-- before they can qualify a new lesson promotion.
ALTER TABLE learning_evaluations
    ADD COLUMN evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE learning_evaluations ADD CONSTRAINT learning_evaluations_evidence_object
    CHECK (jsonb_typeof(evidence) = 'object');
CREATE INDEX edit_runs_lesson_job_idx ON edit_runs(evaluation_lesson_id, job_id)
    WHERE evaluation_lesson_id IS NOT NULL;
