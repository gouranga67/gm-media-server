CREATE TABLE creative_assets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind text NOT NULL CHECK (kind IN ('sound_effect', 'meme_sound', 'sticker', 'gif', 'meme_image')),
    title text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
    creator text NOT NULL DEFAULT '',
    source_name text NOT NULL CHECK (char_length(source_name) BETWEEN 1 AND 255),
    storage_key text NOT NULL UNIQUE,
    sha256 text NOT NULL UNIQUE CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    mime_type text NOT NULL,
    byte_size bigint NOT NULL CHECK (byte_size > 0),
    duration_seconds double precision CHECK (duration_seconds IS NULL OR duration_seconds > 0),
    tags jsonb NOT NULL DEFAULT '[]'::jsonb,
    purpose text NOT NULL DEFAULT 'emphasis' CHECK (purpose IN ('hook', 'transition', 'emphasis', 'reveal', 'reaction', 'payoff')),
    license_name text NOT NULL CHECK (char_length(license_name) BETWEEN 1 AND 200),
    license_source_url text NOT NULL,
    license_proof text NOT NULL DEFAULT '',
    commercial_use boolean NOT NULL DEFAULT false,
    synthetic_media boolean NOT NULL DEFAULT false,
    allowed_platforms jsonb NOT NULL DEFAULT '["all_social"]'::jsonb,
    attribution text NOT NULL DEFAULT '',
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX creative_assets_active_kind_idx ON creative_assets(active, kind, purpose);

ALTER TABLE jobs
    ADD COLUMN selected_music_track_id uuid REFERENCES music_tracks(id) ON DELETE SET NULL,
    ADD COLUMN effect_level text NOT NULL DEFAULT 'off'
        CHECK (effect_level IN ('off', 'subtle', 'social', 'meme_heavy'));

ALTER TABLE edit_runs ADD COLUMN effects_enabled boolean;
