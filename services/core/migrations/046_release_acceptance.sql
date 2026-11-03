-- Keep historical scheduling intent unknown rather than guessing from timestamps.
ALTER TABLE publishing_posts ADD COLUMN schedule_requested boolean;
CREATE TABLE release_observations (
    id uuid PRIMARY KEY,
    build_id text NOT NULL CHECK (build_id ~ '^[0-9a-f]{7,64}$'),
    check_key text NOT NULL,
    result text NOT NULL CHECK (result IN ('pass','fail','not_applicable')),
    note text NOT NULL CHECK (length(note) BETWEEN 8 AND 2000),
    job_id uuid REFERENCES jobs(id),
    edit_run_id uuid REFERENCES edit_runs(id),
    publishing_post_id uuid REFERENCES publishing_posts(id),
    evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence)='object'),
    recorded_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX release_observations_build_check_idx ON release_observations(build_id,check_key,created_at DESC,id);
