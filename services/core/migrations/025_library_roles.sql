-- A human label describes intended use; auto does not guess from missing speech.
ALTER TABLE asset_library_metadata
    ADD COLUMN media_role text NOT NULL DEFAULT 'auto'
    CHECK (media_role IN ('auto', 'talking', 'broll'));
CREATE INDEX asset_library_metadata_role_idx ON asset_library_metadata (media_role);
