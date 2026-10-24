ALTER TABLE jobs
    DROP CONSTRAINT jobs_output_aspect_check;
ALTER TABLE jobs
    ADD CONSTRAINT jobs_output_aspect_check
        CHECK (output_aspect IN ('vertical', 'landscape', 'square'));

CREATE TABLE creative_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 80),
    description text NOT NULL DEFAULT '' CHECK (char_length(description) <= 400),
    recipe text NOT NULL CHECK (recipe IN ('talking_head', 'montage')),
    target_duration_seconds integer NOT NULL
        CHECK (target_duration_seconds IN (15, 20, 30, 45, 60)),
    edit_style text NOT NULL CHECK (edit_style IN ('clean', 'energetic', 'calm')),
    music_mode text NOT NULL CHECK (music_mode IN ('none', 'subtle', 'present')),
    target_platform text NOT NULL CHECK (
        target_platform IN ('all_social', 'facebook', 'instagram', 'linkedin', 'tiktok', 'youtube')
    ),
    output_aspect text NOT NULL CHECK (output_aspect IN ('vertical', 'landscape', 'square')),
    reasoning_effort text NOT NULL CHECK (reasoning_effort IN ('low', 'medium', 'high')),
    source_job_id uuid REFERENCES jobs(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX creative_profiles_name_lower_idx ON creative_profiles (lower(name));
CREATE INDEX creative_profiles_updated_idx ON creative_profiles (updated_at DESC);

ALTER TABLE jobs
    ADD COLUMN creative_profile_id uuid REFERENCES creative_profiles(id) ON DELETE SET NULL;

CREATE TABLE delivery_variants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    edit_run_id uuid NOT NULL REFERENCES edit_runs(id) ON DELETE CASCADE,
    output_aspect text NOT NULL CHECK (output_aspect IN ('vertical', 'landscape', 'square')),
    target_duration_seconds integer NOT NULL CHECK (target_duration_seconds IN (15, 20, 30, 45, 60)),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'rendering', 'ready', 'failed')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    lease_expires_at timestamptz,
    video_path text,
    captions_path text,
    cover_path text,
    post_copy_path text,
    package_path text,
    manifest_path text,
    manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
    error text,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (edit_run_id, output_aspect, target_duration_seconds)
);

CREATE INDEX delivery_variants_status_updated_idx ON delivery_variants(status, updated_at);
CREATE INDEX delivery_variants_job_created_idx ON delivery_variants(job_id, created_at DESC);
