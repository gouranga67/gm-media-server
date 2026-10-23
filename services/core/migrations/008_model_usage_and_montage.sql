ALTER TABLE jobs
    ADD COLUMN editor_model text,
    ADD COLUMN reasoning_effort text NOT NULL DEFAULT 'medium'
        CHECK (reasoning_effort IN ('low', 'medium', 'high')),
    ADD COLUMN output_aspect text NOT NULL DEFAULT 'vertical'
        CHECK (output_aspect IN ('vertical', 'landscape'));

ALTER TABLE jobs DROP CONSTRAINT jobs_target_duration_seconds_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_target_duration_seconds_check
    CHECK (target_duration_seconds IN (15, 20, 30, 45, 60));

ALTER TABLE edit_runs
    ADD COLUMN reasoning_effort text
        CHECK (reasoning_effort IS NULL OR reasoning_effort IN ('low', 'medium', 'high'));

ALTER TABLE music_tracks
    ADD COLUMN beat_grid_seconds jsonb NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE editor_models (
    slug text PRIMARY KEY CHECK (char_length(slug) BETWEEN 1 AND 160),
    display_name text NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 160),
    provider text NOT NULL DEFAULT 'chatgpt_plan',
    available boolean NOT NULL DEFAULT true,
    sort_order integer NOT NULL DEFAULT 0,
    refreshed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ai_usage_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    edit_run_id uuid NOT NULL REFERENCES edit_runs(id) ON DELETE CASCADE,
    provider text NOT NULL,
    model text NOT NULL,
    reasoning_effort text
        CHECK (reasoning_effort IS NULL OR reasoning_effort IN ('low', 'medium', 'high')),
    request_kind text NOT NULL CHECK (request_kind IN ('initial_plan', 'revision')),
    response_id text,
    input_tokens integer NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    cached_input_tokens integer NOT NULL DEFAULT 0 CHECK (cached_input_tokens >= 0),
    output_tokens integer NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    reasoning_tokens integer NOT NULL DEFAULT 0 CHECK (reasoning_tokens >= 0),
    total_tokens integer NOT NULL DEFAULT 0 CHECK (total_tokens >= 0),
    latency_ms integer NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (edit_run_id)
);

CREATE INDEX ai_usage_events_job_created_idx
    ON ai_usage_events(job_id, created_at DESC);
CREATE INDEX ai_usage_events_model_created_idx
    ON ai_usage_events(model, created_at DESC);
CREATE INDEX editor_models_available_order_idx
    ON editor_models(available, sort_order, display_name);
