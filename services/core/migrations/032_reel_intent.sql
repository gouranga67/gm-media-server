-- Editorial purpose is independent of the speech/montage rendering engine.
ALTER TABLE jobs ADD COLUMN reel_intent text NOT NULL DEFAULT 'auto'
    CHECK (reel_intent IN ('auto', 'story', 'promotion', 'bloopers'));

-- Recover the explicit selection for existing concept jobs without inferring it
-- from product names, an effects level or a generated title.
UPDATE jobs SET reel_intent = CASE WHEN requests.reel_kind = 'bloopers' THEN 'bloopers' ELSE 'story' END
FROM reel_concept_jobs selected
JOIN reel_concept_requests requests ON requests.id = selected.request_id
WHERE jobs.id = selected.job_id;
