-- Pin immutable timing snapshots to a plan. Later library analysis must never
-- alter the source timings of a saved/approved cut or its delivery variants.
ALTER TABLE edit_plans
    ADD COLUMN speech_precision_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE edit_plans ADD CONSTRAINT edit_plans_speech_precision_object
    CHECK (jsonb_typeof(speech_precision_snapshot) = 'object');
