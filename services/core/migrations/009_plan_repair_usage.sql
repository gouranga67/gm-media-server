ALTER TABLE ai_usage_events
    DROP CONSTRAINT ai_usage_events_edit_run_id_key;

ALTER TABLE ai_usage_events
    DROP CONSTRAINT ai_usage_events_request_kind_check;

ALTER TABLE ai_usage_events
    ADD CONSTRAINT ai_usage_events_request_kind_check
    CHECK (request_kind IN ('initial_plan', 'revision', 'repair'));

CREATE INDEX ai_usage_events_edit_run_id_idx
    ON ai_usage_events(edit_run_id, created_at);
