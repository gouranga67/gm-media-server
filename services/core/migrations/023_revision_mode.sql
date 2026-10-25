ALTER TABLE edit_runs ADD COLUMN revision_mode text NOT NULL DEFAULT 'targeted'
    CHECK (revision_mode IN ('targeted', 'rebuild_story'));
