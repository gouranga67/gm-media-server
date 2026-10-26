ALTER TABLE jobs DROP CONSTRAINT jobs_edit_style_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_edit_style_check
    CHECK (edit_style IN ('clean', 'energetic', 'calm', 'high_impact'));

ALTER TABLE creative_profiles DROP CONSTRAINT creative_profiles_edit_style_check;
ALTER TABLE creative_profiles ADD CONSTRAINT creative_profiles_edit_style_check
    CHECK (edit_style IN ('clean', 'energetic', 'calm', 'high_impact'));

ALTER TABLE edit_runs ADD COLUMN broll_enabled boolean;
