-- Cursor pages and complete readiness read metadata, not preview files.
CREATE INDEX edit_runs_lesson_history_idx
    ON edit_runs(evaluation_lesson_id, created_at DESC, id DESC)
    INCLUDE (status, evaluation_case_id)
    WHERE evaluation_lesson_id IS NOT NULL;
