CREATE TABLE asset_storage_optimizations (
    asset_id uuid PRIMARY KEY REFERENCES assets(id) ON DELETE RESTRICT,
    canonical_asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    method text NOT NULL DEFAULT 'hardlink' CHECK (method = 'hardlink'),
    bytes_reclaimed bigint NOT NULL DEFAULT 0 CHECK (bytes_reclaimed >= 0),
    source_storage_key text NOT NULL,
    canonical_storage_key text NOT NULL,
    device bigint NOT NULL,
    inode bigint NOT NULL,
    reason text NOT NULL CHECK (reason IN ('reviewed_cleanup', 'upload_exact_match')),
    optimized_at timestamptz NOT NULL DEFAULT now(),
    CHECK (asset_id <> canonical_asset_id)
);

CREATE INDEX asset_storage_optimizations_canonical_idx
    ON asset_storage_optimizations (canonical_asset_id, optimized_at DESC);

CREATE INDEX asset_storage_optimizations_sha256_idx
    ON asset_storage_optimizations (sha256, optimized_at DESC);
