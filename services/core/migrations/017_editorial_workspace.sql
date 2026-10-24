CREATE TABLE brand_kits (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 80),
    primary_color text NOT NULL DEFAULT '#173F5F' CHECK (primary_color ~ '^#[0-9A-Fa-f]{6}$'),
    accent_color text NOT NULL DEFAULT '#4BA3D3' CHECK (accent_color ~ '^#[0-9A-Fa-f]{6}$'),
    caption_style text NOT NULL DEFAULT 'bold' CHECK (caption_style IN ('clean', 'bold', 'minimal')),
    font_family text NOT NULL DEFAULT 'sans' CHECK (font_family IN ('sans', 'serif', 'mono')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX brand_kits_name_lower_idx ON brand_kits (lower(name));

ALTER TABLE jobs
    ADD COLUMN brand_kit_id uuid REFERENCES brand_kits(id) ON DELETE SET NULL,
    ADD COLUMN cover_time_seconds numeric(8,3) NOT NULL DEFAULT 1 CHECK (cover_time_seconds >= 0),
    ADD COLUMN publishing_preset text NOT NULL DEFAULT 'custom'
        CHECK (publishing_preset IN ('custom', 'instagram_reel', 'tiktok', 'youtube_short', 'linkedin_landscape', 'facebook_square'));

ALTER TABLE creative_profiles
    ADD COLUMN brand_kit_id uuid REFERENCES brand_kits(id) ON DELETE SET NULL,
    ADD COLUMN publishing_preset text NOT NULL DEFAULT 'custom'
        CHECK (publishing_preset IN ('custom', 'instagram_reel', 'tiktok', 'youtube_short', 'linkedin_landscape', 'facebook_square'));

ALTER TABLE edit_runs
    ADD COLUMN clip_adjustments jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN locked_elements jsonb NOT NULL DEFAULT '[]'::jsonb;
