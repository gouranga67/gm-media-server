CREATE TABLE source_products (
    id uuid PRIMARY KEY,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    aliases text[] NOT NULL DEFAULT ARRAY[]::text[] CHECK (cardinality(aliases)<=20),
    notes text NOT NULL DEFAULT '' CHECK (length(notes)<=2000),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX source_products_name_idx ON source_products(lower(name));

CREATE TABLE asset_range_annotations (
    id uuid PRIMARY KEY,
    asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    start_seconds double precision NOT NULL CHECK (start_seconds>=0 AND start_seconds<'Infinity'::float8),
    end_seconds double precision NOT NULL CHECK (end_seconds>start_seconds AND end_seconds<'Infinity'::float8),
    role text NOT NULL CHECK (role IN ('talking','broll','product','reaction','avoid')),
    note text NOT NULL DEFAULT '' CHECK (length(note)<=1200),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX asset_range_annotations_asset_idx ON asset_range_annotations(asset_id,start_seconds);
