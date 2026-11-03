-- Saved review context; older auto-sort sessions remain names-only.
ALTER TABLE library_organization_requests
    ADD COLUMN include_folders boolean NOT NULL DEFAULT false,
    ADD COLUMN folder_options jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(folder_options) = 'array' AND jsonb_array_length(folder_options) <= 100);
