-- Discovery is separate from editing history: ideas create jobs only on selection.
CREATE TABLE reel_concept_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    focus text NOT NULL DEFAULT '' CHECK (char_length(focus) <= 1200),
    audience text NOT NULL DEFAULT '' CHECK (char_length(audience) <= 600),
    collection_id uuid REFERENCES library_collections(id) ON DELETE SET NULL,
    privacy_mode text NOT NULL CHECK (privacy_mode IN ('hybrid', 'text_only')),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','generating','ready','failed')),
    inventory jsonb NOT NULL,
    concepts jsonb NOT NULL DEFAULT '[]'::jsonb,
    coverage jsonb NOT NULL DEFAULT '{}'::jsonb,
    model text,
    total_tokens integer NOT NULL DEFAULT 0 CHECK (total_tokens >= 0),
    error text,
    lease_expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX reel_concept_requests_pending_idx ON reel_concept_requests(status, created_at);
CREATE INDEX reel_concept_requests_recent_idx ON reel_concept_requests(created_at DESC);
CREATE TABLE reel_concept_jobs (
    request_id uuid NOT NULL REFERENCES reel_concept_requests(id) ON DELETE CASCADE,
    concept_id uuid NOT NULL,
    job_id uuid NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(request_id, concept_id)
);

-- Concept calls count toward the same measured usage and studio token budgets.
ALTER TABLE ai_usage_events
    ALTER COLUMN job_id DROP NOT NULL,
    ALTER COLUMN edit_run_id DROP NOT NULL,
    ADD COLUMN concept_request_id uuid REFERENCES reel_concept_requests(id) ON DELETE CASCADE,
    DROP CONSTRAINT ai_usage_events_request_kind_check;
ALTER TABLE ai_usage_events ADD CONSTRAINT ai_usage_events_request_kind_check
    CHECK (request_kind IN ('initial_plan','revision','repair','concepts'));
ALTER TABLE ai_usage_events ADD CONSTRAINT ai_usage_events_source_check CHECK (
    (request_kind='concepts' AND concept_request_id IS NOT NULL AND job_id IS NULL AND edit_run_id IS NULL)
    OR (request_kind<>'concepts' AND concept_request_id IS NULL AND job_id IS NOT NULL AND edit_run_id IS NOT NULL)
);
CREATE INDEX ai_usage_events_concept_idx ON ai_usage_events(concept_request_id) WHERE concept_request_id IS NOT NULL;
