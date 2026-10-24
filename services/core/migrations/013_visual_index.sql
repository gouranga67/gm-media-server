CREATE TABLE asset_visual_indexes (
    asset_id uuid PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
    canonical_asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'ready', 'failed', 'aliased')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    lease_expires_at timestamptz,
    model_id text NOT NULL DEFAULT 'openai/clip-vit-base-patch32',
    model_revision text NOT NULL DEFAULT 'c7244be81152024ce0e99ac8d2e373a8953d9f9a',
    index_version text NOT NULL DEFAULT '1.0',
    vector_dimension integer NOT NULL DEFAULT 512 CHECK (vector_dimension > 0),
    frame_count integer NOT NULL DEFAULT 0 CHECK (frame_count >= 0),
    error text,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE asset_visual_embeddings (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    segment_kind text NOT NULL CHECK (segment_kind IN ('scene', 'image')),
    segment_index integer NOT NULL CHECK (segment_index >= 0),
    frame_index integer NOT NULL CHECK (frame_index >= 0),
    start_seconds double precision NOT NULL DEFAULT 0 CHECK (start_seconds >= 0),
    end_seconds double precision NOT NULL DEFAULT 0 CHECK (end_seconds >= start_seconds),
    frame_seconds double precision NOT NULL DEFAULT 0 CHECK (frame_seconds >= 0),
    frame_path text NOT NULL,
    embedding real[] NOT NULL,
    source_model text NOT NULL,
    model_revision text NOT NULL,
    index_version text NOT NULL DEFAULT '1.0',
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (array_length(embedding, 1) = 512),
    UNIQUE (asset_id, segment_kind, segment_index, frame_index)
);

CREATE INDEX asset_visual_indexes_status_updated_idx
    ON asset_visual_indexes (status, updated_at);

CREATE INDEX asset_visual_indexes_canonical_idx
    ON asset_visual_indexes (canonical_asset_id, status);

CREATE INDEX asset_visual_embeddings_asset_time_idx
    ON asset_visual_embeddings (asset_id, start_seconds, end_seconds);

CREATE INDEX asset_visual_embeddings_project_idx
    ON asset_visual_embeddings (project_id);

INSERT INTO asset_visual_indexes (asset_id, canonical_asset_id, status)
SELECT assets.id, assets.id, 'pending'
FROM assets
JOIN asset_ingests ON asset_ingests.asset_id = assets.id
JOIN asset_catalogs ON asset_catalogs.asset_id = assets.id
WHERE assets.status = 'ready'
  AND assets.library_status = 'active'
  AND asset_ingests.status = 'ready'
  AND asset_catalogs.status = 'ready'
  AND (assets.mime_type LIKE 'video/%' OR assets.mime_type LIKE 'image/%')
ON CONFLICT (asset_id) DO NOTHING;
