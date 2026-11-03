-- Server-resolved source targets are frozen before the worker/render starts.
ALTER TABLE edit_runs ADD COLUMN revision_resolution jsonb;
ALTER TABLE edit_runs ADD CONSTRAINT edit_runs_revision_resolution_object
    CHECK (revision_resolution IS NULL OR jsonb_typeof(revision_resolution) = 'object');
