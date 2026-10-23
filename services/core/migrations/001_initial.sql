CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 160),
    brief text NOT NULL DEFAULT '',
    privacy_mode text NOT NULL DEFAULT 'hybrid'
        CHECK (privacy_mode IN ('hybrid', 'text_only', 'local_only')),
    ai_copy_allowed boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE assets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_name text NOT NULL,
    storage_key text NOT NULL UNIQUE,
    sha256 text CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
    mime_type text,
    byte_size bigint CHECK (byte_size IS NULL OR byte_size >= 0),
    status text NOT NULL DEFAULT 'uploading'
        CHECK (status IN ('uploading', 'uploaded', 'quarantined', 'ready', 'failed')),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    recipe text NOT NULL,
    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN (
            'draft', 'uploading', 'ingesting', 'analyzing', 'planning',
            'previewing', 'awaiting_review', 'rendering', 'complete', 'failed', 'cancelled'
        )),
    revision integer NOT NULL DEFAULT 0 CHECK (revision >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE job_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    event_type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE edit_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    version integer NOT NULL CHECK (version > 0),
    schema_version text NOT NULL,
    document jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (job_id, version)
);

CREATE TABLE approvals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    edit_plan_id uuid REFERENCES edit_plans(id) ON DELETE SET NULL,
    decision text NOT NULL CHECK (decision IN ('approved', 'revision_requested', 'rejected')),
    note text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX assets_project_id_idx ON assets(project_id);
CREATE INDEX jobs_project_id_idx ON jobs(project_id);
CREATE INDEX jobs_status_idx ON jobs(status);
CREATE INDEX job_events_job_id_id_idx ON job_events(job_id, id);
