CREATE TABLE studio_members (
    login text PRIMARY KEY CHECK (login = lower(login) AND char_length(login) BETWEEN 3 AND 320),
    display_name text NOT NULL DEFAULT '' CHECK (char_length(display_name) <= 120),
    role text NOT NULL CHECK (role IN ('owner', 'editor', 'viewer')),
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX studio_single_owner_idx ON studio_members (role) WHERE role = 'owner';

CREATE TABLE studio_settings (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    studio_name text NOT NULL DEFAULT 'GM Studio' CHECK (char_length(studio_name) BETWEEN 1 AND 80),
    onboarding_completed boolean NOT NULL DEFAULT false,
    daily_ai_token_limit bigint NOT NULL DEFAULT 0 CHECK (daily_ai_token_limit >= 0),
    monthly_ai_token_limit bigint NOT NULL DEFAULT 0 CHECK (monthly_ai_token_limit >= 0),
    max_active_jobs integer NOT NULL DEFAULT 2 CHECK (max_active_jobs BETWEEN 1 AND 20),
    preview_retention_days integer NOT NULL DEFAULT 30 CHECK (preview_retention_days BETWEEN 1 AND 3650),
    delivery_retention_days integer NOT NULL DEFAULT 90 CHECK (delivery_retention_days BETWEEN 1 AND 3650),
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO studio_settings (singleton) VALUES (true);

CREATE TABLE studio_audit_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_login text NOT NULL DEFAULT 'system',
    action text NOT NULL CHECK (char_length(action) BETWEEN 1 AND 120),
    target_type text NOT NULL DEFAULT '',
    target_id text NOT NULL DEFAULT '',
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX studio_audit_events_created_idx ON studio_audit_events (created_at DESC);

CREATE TABLE retention_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_login text NOT NULL,
    preview_files_removed integer NOT NULL DEFAULT 0 CHECK (preview_files_removed >= 0),
    delivery_files_removed integer NOT NULL DEFAULT 0 CHECK (delivery_files_removed >= 0),
    bytes_reclaimed bigint NOT NULL DEFAULT 0 CHECK (bytes_reclaimed >= 0),
    originals_removed integer NOT NULL DEFAULT 0 CHECK (originals_removed = 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE jobs
    ADD COLUMN created_by_login text,
    ADD COLUMN archived_at timestamptz;

CREATE INDEX jobs_archived_created_idx ON jobs (archived_at, created_at DESC);
