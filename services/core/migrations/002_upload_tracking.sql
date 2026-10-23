ALTER TABLE assets
    ADD COLUMN tus_upload_id text UNIQUE,
    ADD COLUMN tus_storage_key text,
    ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();

CREATE INDEX assets_status_idx ON assets(status);
