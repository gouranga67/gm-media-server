-- Groupings only: originals and historical memberships never move on disk.
ALTER TABLE library_collections
    ADD COLUMN parent_id uuid REFERENCES library_collections(id) ON DELETE RESTRICT,
    ADD CONSTRAINT library_collection_not_own_parent CHECK (parent_id IS DISTINCT FROM id);
CREATE INDEX library_collections_parent_idx ON library_collections(parent_id);
