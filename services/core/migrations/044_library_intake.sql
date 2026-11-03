-- Only new standalone imports enter the Inbox. Existing media stays reviewed.
CREATE TABLE library_intakes (
    asset_id uuid PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
    preferences jsonb NOT NULL DEFAULT '{}'::jsonb,
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX library_intakes_unreviewed_idx ON library_intakes(created_at DESC, asset_id)
    WHERE reviewed_at IS NULL;
