ALTER TABLE assets
    ADD COLUMN library_status text NOT NULL DEFAULT 'active'
        CHECK (library_status IN ('active', 'archived'));

-- A reusable original must not disappear because its original project is
-- removed. Explicit original deletion will be introduced with retention and
-- backup checks; until then the database safely refuses that cascade.
ALTER TABLE assets
    DROP CONSTRAINT assets_project_id_fkey,
    ADD CONSTRAINT assets_project_id_fkey
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT;

ALTER TABLE asset_ingests
    DROP CONSTRAINT asset_ingests_project_id_fkey,
    ADD CONSTRAINT asset_ingests_project_id_fkey
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT;

CREATE INDEX assets_library_status_created_idx
    ON assets (library_status, status, created_at DESC);
