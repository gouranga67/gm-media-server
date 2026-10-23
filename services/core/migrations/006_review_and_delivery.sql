ALTER TABLE jobs DROP CONSTRAINT jobs_status_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_status_check CHECK (status IN (
    'draft', 'uploading', 'ingesting', 'analyzing', 'planning',
    'previewing', 'awaiting_review', 'revising', 'approved',
    'rendering', 'exporting', 'delivered', 'complete', 'failed', 'cancelled'
));

ALTER TABLE edit_runs
    ADD COLUMN based_on_run_id uuid REFERENCES edit_runs(id) ON DELETE SET NULL,
    ADD COLUMN revision_note text,
    ADD COLUMN caption_corrections jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN approved_at timestamptz;

CREATE TABLE final_exports (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    edit_run_id uuid NOT NULL UNIQUE REFERENCES edit_runs(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'rendering', 'ready', 'failed')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    lease_expires_at timestamptz,
    video_path text,
    captions_path text,
    cover_path text,
    post_copy_path text,
    package_path text,
    manifest_path text,
    manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
    error text,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX edit_runs_based_on_run_id_idx ON edit_runs(based_on_run_id);
CREATE INDEX final_exports_status_updated_idx ON final_exports(status, updated_at);
CREATE INDEX final_exports_job_id_created_idx ON final_exports(job_id, created_at DESC);
