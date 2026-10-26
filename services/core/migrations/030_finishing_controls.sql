ALTER TABLE edit_runs ADD COLUMN finishing_settings jsonb;
ALTER TABLE edit_runs ADD CONSTRAINT edit_runs_finishing_object CHECK (finishing_settings IS NULL OR jsonb_typeof(finishing_settings)='object');
