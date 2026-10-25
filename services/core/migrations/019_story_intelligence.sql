ALTER TABLE jobs
    ADD COLUMN audience text NOT NULL DEFAULT '' CHECK (char_length(audience) <= 600),
    ADD COLUMN story_goal text NOT NULL DEFAULT '' CHECK (char_length(story_goal) <= 1200),
    ADD COLUMN desired_feeling text NOT NULL DEFAULT '' CHECK (char_length(desired_feeling) <= 600),
    ADD COLUMN ending_instruction text NOT NULL DEFAULT '' CHECK (char_length(ending_instruction) <= 600);

CREATE TABLE asset_story_indexes (
    asset_id uuid PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'ready', 'failed')),
    story_version text NOT NULL DEFAULT '1.0',
    moment_count integer NOT NULL DEFAULT 0 CHECK (moment_count >= 0),
    moments jsonb NOT NULL DEFAULT '[]'::jsonb,
    error text,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX asset_story_indexes_status_updated_idx
    ON asset_story_indexes (status, updated_at);

INSERT INTO asset_story_indexes (asset_id, status)
SELECT asset_catalogs.asset_id, 'pending'
FROM asset_catalogs
WHERE asset_catalogs.status = 'ready'
ON CONFLICT (asset_id) DO NOTHING;

-- Rebuild existing catalogues once so every active source receives the local,
-- source-timestamped Phase 13 story index. This does not call a hosted model.
UPDATE asset_catalogs
SET status = 'pending', attempts = 0, lease_expires_at = NULL,
    error = NULL, completed_at = NULL, updated_at = now();
