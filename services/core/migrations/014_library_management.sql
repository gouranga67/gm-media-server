CREATE TABLE asset_library_metadata (
    asset_id uuid PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
    display_name text,
    notes text NOT NULL DEFAULT '',
    favorite boolean NOT NULL DEFAULT false,
    tags text[] NOT NULL DEFAULT ARRAY[]::text[],
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (display_name IS NULL OR length(display_name) BETWEEN 1 AND 255),
    CHECK (length(notes) <= 4000),
    CHECK (cardinality(tags) <= 25)
);

CREATE INDEX asset_library_metadata_favorite_idx
    ON asset_library_metadata (favorite, updated_at DESC)
    WHERE favorite = true;

CREATE INDEX asset_library_metadata_tags_idx
    ON asset_library_metadata USING gin (tags);

CREATE TABLE library_collections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    description text NOT NULL DEFAULT '' CHECK (length(description) <= 1000),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX library_collections_name_unique_idx
    ON library_collections (lower(name));

CREATE TABLE library_collection_assets (
    collection_id uuid NOT NULL REFERENCES library_collections(id) ON DELETE CASCADE,
    asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    position integer NOT NULL DEFAULT 0 CHECK (position >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (collection_id, asset_id)
);

CREATE INDEX library_collection_assets_asset_idx
    ON library_collection_assets (asset_id, collection_id);

