CREATE TABLE asset_ingests (
    asset_id uuid PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'ready', 'failed')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    lease_expires_at timestamptz,
    manifest_path text,
    manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
    error text,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX asset_ingests_status_updated_idx ON asset_ingests(status, updated_at);
CREATE INDEX asset_ingests_project_id_idx ON asset_ingests(project_id);
