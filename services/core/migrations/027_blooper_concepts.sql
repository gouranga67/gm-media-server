ALTER TABLE reel_concept_requests ADD COLUMN reel_kind text NOT NULL DEFAULT 'story'
    CHECK (reel_kind IN ('story', 'bloopers'));
