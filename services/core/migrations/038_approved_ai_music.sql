-- AI-labelled music is usable only after explicit owner approval on import.
-- This exception does not change original-media or creative-effect policies.
ALTER TABLE music_tracks DROP CONSTRAINT music_tracks_synthetic_media_check;
ALTER TABLE music_tracks ADD COLUMN synthetic_music_approved boolean NOT NULL DEFAULT false;
ALTER TABLE music_tracks ADD CONSTRAINT music_tracks_synthetic_approval_check
    CHECK (NOT synthetic_music_approved OR synthetic_media);
