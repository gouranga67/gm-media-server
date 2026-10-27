-- Publishing is always a separately approved operation on a completed export.
CREATE TABLE social_connections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    platform text NOT NULL CHECK (platform IN ('instagram','facebook')),
    external_id text NOT NULL CHECK (external_id ~ '^[0-9]+$'),
    display_name text NOT NULL,
    token_ciphertext text NOT NULL,
    token_expires_at timestamptz,
    active boolean NOT NULL DEFAULT true,
    connected_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(platform,external_id)
);
CREATE TABLE social_oauth_states (
    state_hash text PRIMARY KEY,
    actor_login text NOT NULL,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE publishing_drafts (
    id uuid PRIMARY KEY,
    final_export_id uuid NOT NULL REFERENCES final_exports(id),
    video_sha256 text NOT NULL CHECK (video_sha256 ~ '^[a-f0-9]{64}$'),
    caption text NOT NULL DEFAULT '' CHECK (char_length(caption)<=2200),
    revision integer NOT NULL DEFAULT 1 CHECK (revision>0),
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE publishing_posts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id uuid NOT NULL REFERENCES publishing_drafts(id),
    connection_id uuid NOT NULL REFERENCES social_connections(id),
    approval_request_id uuid NOT NULL,
    approved_revision integer NOT NULL,
    approved_by text NOT NULL,
    publish_at timestamptz NOT NULL,
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','uploading','processing','publishing','published','failed','unknown','cancelled')),
    remote_container_id text,
    remote_media_id text,
    publish_started_at timestamptz,
    upload_uri text,
    permalink text,
    error text,
    checks integer NOT NULL DEFAULT 0,
    next_check_at timestamptz NOT NULL DEFAULT now(),
    lease_expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(draft_id,connection_id)
);
CREATE INDEX publishing_posts_queue_idx ON publishing_posts(status,next_check_at,publish_at);
CREATE TABLE publishing_caption_requests (
    id uuid PRIMARY KEY,
    draft_id uuid NOT NULL REFERENCES publishing_drafts(id),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','generating','ready','failed')),
    options jsonb NOT NULL DEFAULT '[]'::jsonb,
    error text,
    total_tokens integer NOT NULL DEFAULT 0,
    lease_expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE ai_usage_events ADD COLUMN publishing_caption_request_id uuid REFERENCES publishing_caption_requests(id);
ALTER TABLE ai_usage_events DROP CONSTRAINT ai_usage_events_request_kind_check, DROP CONSTRAINT ai_usage_events_source_check;
ALTER TABLE ai_usage_events ADD CONSTRAINT ai_usage_events_request_kind_check CHECK (request_kind IN ('initial_plan','revision','repair','concepts','organization','post_caption'));
ALTER TABLE ai_usage_events ADD CONSTRAINT ai_usage_events_source_check CHECK (
    (request_kind='post_caption' AND publishing_caption_request_id IS NOT NULL AND concept_request_id IS NULL AND organization_request_id IS NULL AND job_id IS NULL AND edit_run_id IS NULL)
    OR (publishing_caption_request_id IS NULL AND (
      (request_kind='concepts' AND concept_request_id IS NOT NULL AND organization_request_id IS NULL AND job_id IS NULL AND edit_run_id IS NULL)
      OR (request_kind='organization' AND organization_request_id IS NOT NULL AND concept_request_id IS NULL AND job_id IS NULL AND edit_run_id IS NULL)
      OR (request_kind IN ('initial_plan','revision','repair') AND concept_request_id IS NULL AND organization_request_id IS NULL AND job_id IS NOT NULL AND edit_run_id IS NOT NULL)
    ))
);
