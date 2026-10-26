ALTER TABLE jobs
    ADD COLUMN assembly_mode text NOT NULL DEFAULT 'talking_head'
        CHECK (assembly_mode IN ('auto','talking_head','montage')),
    ADD COLUMN pacing_mode text NOT NULL DEFAULT 'manual'
        CHECK (pacing_mode IN ('auto','manual')),
    ADD COLUMN assembly_decision jsonb;

-- Existing jobs keep their engine and pacing. Never reinterpret frozen plans.
UPDATE jobs SET assembly_mode=recipe,
    assembly_decision=jsonb_build_object('version',1,'mode',recipe,'recipe',recipe,
        'edit_style',edit_style,'purpose',reel_intent,'reason','Existing edit format retained.',
        'label',CASE WHEN recipe='montage' THEN 'Visual sequence' ELSE 'Speech with supporting pictures' END,
        'warnings','[]'::jsonb,'hosted_model_calls',0);
