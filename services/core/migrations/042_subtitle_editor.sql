-- Subtitle text/layout is versioned separately from the trusted media edit.
ALTER TABLE edit_plans ADD COLUMN subtitle_document jsonb;
ALTER TABLE edit_plans ADD CONSTRAINT edit_plans_subtitle_document_object
    CHECK (subtitle_document IS NULL OR jsonb_typeof(subtitle_document) = 'object');
CREATE TABLE subtitle_drafts (
    edit_run_id uuid PRIMARY KEY REFERENCES edit_runs(id) ON DELETE CASCADE,
    revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
    document jsonb NOT NULL CHECK (jsonb_typeof(document) = 'object'),
    applied_run_id uuid REFERENCES edit_runs(id) ON DELETE SET NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
