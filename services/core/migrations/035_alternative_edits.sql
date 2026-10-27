-- Creative alternatives are distinct from corrections and exact re-renders.
ALTER TABLE edit_runs
    ADD COLUMN alternative_kind text CHECK (alternative_kind IN ('different_cut','different_story')),
    ADD COLUMN alternative_request_id uuid,
    ADD CONSTRAINT edit_runs_alternative_request_check CHECK (
        (alternative_kind IS NULL AND alternative_request_id IS NULL)
        OR (alternative_kind IS NOT NULL AND alternative_request_id IS NOT NULL AND based_on_run_id IS NOT NULL)
    );
CREATE UNIQUE INDEX edit_runs_alternative_request_idx
    ON edit_runs(job_id,alternative_request_id) WHERE alternative_request_id IS NOT NULL;
