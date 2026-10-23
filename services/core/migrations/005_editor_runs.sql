CREATE TABLE job_assets (
    job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (job_id, asset_id)
);

-- Existing projects created by the Phase 3 phone flow have one job. Attach
-- their assets without guessing when a project already contains multiple jobs.
INSERT INTO job_assets (job_id, asset_id)
SELECT jobs.id, assets.id
FROM jobs
JOIN assets ON assets.project_id = jobs.project_id
WHERE (
    SELECT count(*)
    FROM jobs AS project_jobs
    WHERE project_jobs.project_id = jobs.project_id
) = 1
ON CONFLICT DO NOTHING;

ALTER TABLE edit_plans
    ADD COLUMN provider text NOT NULL DEFAULT 'unknown',
    ADD COLUMN model text NOT NULL DEFAULT 'unknown',
    ADD COLUMN document_sha256 text
        CHECK (document_sha256 IS NULL OR document_sha256 ~ '^[0-9a-f]{64}$');

CREATE TABLE edit_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    version integer NOT NULL CHECK (version > 0),
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'planning', 'rendering', 'ready', 'failed')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    lease_expires_at timestamptz,
    edit_plan_id uuid REFERENCES edit_plans(id) ON DELETE SET NULL,
    provider text,
    model text,
    preview_path text,
    manifest_path text,
    manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
    error text,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (job_id, version)
);

CREATE INDEX job_assets_asset_id_idx ON job_assets(asset_id);
CREATE INDEX edit_runs_status_updated_idx ON edit_runs(status, updated_at);
CREATE INDEX edit_runs_job_id_version_idx ON edit_runs(job_id, version DESC);
