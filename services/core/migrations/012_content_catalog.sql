CREATE TABLE asset_catalogs (
    asset_id uuid PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'ready', 'failed')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    lease_expires_at timestamptz,
    catalog_version text NOT NULL DEFAULT '1.0',
    segment_count integer NOT NULL DEFAULT 0 CHECK (segment_count >= 0),
    transcript_segment_count integer NOT NULL DEFAULT 0
        CHECK (transcript_segment_count >= 0),
    scene_segment_count integer NOT NULL DEFAULT 0
        CHECK (scene_segment_count >= 0),
    error text,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE asset_catalog_segments (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    segment_kind text NOT NULL
        CHECK (segment_kind IN ('asset', 'transcript', 'scene', 'image')),
    segment_index integer NOT NULL CHECK (segment_index >= 0),
    start_seconds double precision NOT NULL DEFAULT 0 CHECK (start_seconds >= 0),
    end_seconds double precision NOT NULL DEFAULT 0 CHECK (end_seconds >= start_seconds),
    text text NOT NULL DEFAULT '',
    facts jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_model text NOT NULL,
    catalog_version text NOT NULL DEFAULT '1.0',
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(text, ''))
    ) STORED,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (asset_id, segment_kind, segment_index)
);

CREATE INDEX asset_catalogs_status_updated_idx
    ON asset_catalogs (status, updated_at);

CREATE INDEX asset_catalog_segments_asset_time_idx
    ON asset_catalog_segments (asset_id, start_seconds, end_seconds);

CREATE INDEX asset_catalog_segments_project_idx
    ON asset_catalog_segments (project_id);

CREATE INDEX asset_catalog_segments_search_idx
    ON asset_catalog_segments USING gin (search_vector);

INSERT INTO asset_catalogs (asset_id, status)
SELECT asset_ingests.asset_id, 'pending'
FROM asset_ingests
JOIN assets ON assets.id = asset_ingests.asset_id
WHERE asset_ingests.status = 'ready'
  AND assets.status = 'ready'
ON CONFLICT (asset_id) DO NOTHING;
