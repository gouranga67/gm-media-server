ALTER TABLE edit_runs
    ADD COLUMN caption_settings jsonb NOT NULL DEFAULT '{}'::jsonb;
