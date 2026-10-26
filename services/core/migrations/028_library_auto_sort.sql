ALTER TABLE asset_library_metadata ADD COLUMN media_category text NOT NULL DEFAULT 'auto'
    CHECK (media_category IN ('auto','review','product','scene','document','other'));
CREATE INDEX asset_library_metadata_category_idx ON asset_library_metadata(media_category);

CREATE TABLE library_organization_requests (
    id uuid PRIMARY KEY,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','generating','ready','failed')),
    asset_ids jsonb NOT NULL,
    rename_existing boolean NOT NULL DEFAULT false,
    privacy_mode text NOT NULL DEFAULT 'hybrid' CHECK (privacy_mode IN ('hybrid','text_only')),
    inventory jsonb NOT NULL,
    suggestions jsonb NOT NULL DEFAULT '[]'::jsonb,
    applied_asset_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    total_tokens integer NOT NULL DEFAULT 0 CHECK (total_tokens >= 0),
    model text,
    error text,
    lease_expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX library_organization_pending_idx ON library_organization_requests(status,created_at);

ALTER TABLE ai_usage_events ADD COLUMN organization_request_id uuid REFERENCES library_organization_requests(id) ON DELETE CASCADE;
ALTER TABLE ai_usage_events DROP CONSTRAINT ai_usage_events_request_kind_check,
    DROP CONSTRAINT ai_usage_events_source_check;
ALTER TABLE ai_usage_events ADD CONSTRAINT ai_usage_events_request_kind_check
    CHECK (request_kind IN ('initial_plan','revision','repair','concepts','organization'));
ALTER TABLE ai_usage_events ADD CONSTRAINT ai_usage_events_source_check CHECK (
    (request_kind='concepts' AND concept_request_id IS NOT NULL AND organization_request_id IS NULL AND job_id IS NULL AND edit_run_id IS NULL)
    OR (request_kind='organization' AND organization_request_id IS NOT NULL AND concept_request_id IS NULL AND job_id IS NULL AND edit_run_id IS NULL)
    OR (request_kind IN ('initial_plan','revision','repair') AND concept_request_id IS NULL AND organization_request_id IS NULL AND job_id IS NOT NULL AND edit_run_id IS NOT NULL)
);
CREATE INDEX ai_usage_events_organization_idx ON ai_usage_events(organization_request_id) WHERE organization_request_id IS NOT NULL;
