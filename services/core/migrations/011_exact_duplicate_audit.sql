CREATE TABLE asset_duplicate_reviews (
    sha256 text PRIMARY KEY
        CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    canonical_asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
    asset_count integer NOT NULL CHECK (asset_count >= 2),
    reviewed_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX asset_duplicate_reviews_canonical_idx
    ON asset_duplicate_reviews (canonical_asset_id);

-- Exact groups are resolved entirely from verified ingest hashes. This index
-- keeps the audit cheap without introducing a second source of truth.
CREATE INDEX assets_ready_sha256_idx
    ON assets (sha256, created_at, id)
    WHERE status = 'ready' AND sha256 IS NOT NULL;
