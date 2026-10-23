ALTER TABLE jobs
    ADD COLUMN target_duration_seconds integer
        CHECK (target_duration_seconds IN (20, 30, 45, 60)),
    ADD COLUMN edit_style text
        CHECK (edit_style IN ('clean', 'energetic', 'calm')),
    ADD COLUMN music_mode text
        CHECK (music_mode IN ('none', 'subtle', 'present')),
    ADD COLUMN target_platform text
        CHECK (target_platform IN (
            'all_social', 'facebook', 'instagram', 'linkedin', 'tiktok', 'youtube'
        )),
    ADD COLUMN must_include text NOT NULL DEFAULT '';

CREATE TABLE music_tracks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
    artist text NOT NULL DEFAULT '',
    storage_key text NOT NULL UNIQUE,
    sha256 text NOT NULL UNIQUE CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    duration_seconds double precision NOT NULL CHECK (duration_seconds > 0),
    mood text NOT NULL CHECK (char_length(mood) BETWEEN 1 AND 80),
    energy text NOT NULL CHECK (energy IN ('low', 'medium', 'high')),
    bpm numeric(6, 2) CHECK (bpm IS NULL OR bpm BETWEEN 30 AND 240),
    license_name text NOT NULL CHECK (char_length(license_name) BETWEEN 1 AND 200),
    license_source_url text NOT NULL,
    license_proof text NOT NULL DEFAULT '',
    commercial_use boolean NOT NULL DEFAULT false,
    synthetic_media boolean NOT NULL DEFAULT false CHECK (synthetic_media = false),
    allowed_platforms jsonb NOT NULL DEFAULT '[]'::jsonb,
    attribution text NOT NULL DEFAULT '',
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX music_tracks_active_mood_idx ON music_tracks(active, mood);
