CREATE TABLE learning_settings (
    id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    enabled boolean NOT NULL DEFAULT true,
    minimum_samples integer NOT NULL DEFAULT 3 CHECK (minimum_samples BETWEEN 3 AND 20),
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO learning_settings (id) VALUES (1)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE edit_feedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    edit_run_id uuid NOT NULL REFERENCES edit_runs(id) ON DELETE CASCADE,
    rating smallint NOT NULL CHECK (rating BETWEEN 1 AND 5),
    tags jsonb NOT NULL DEFAULT '[]'::jsonb,
    note text NOT NULL DEFAULT '' CHECK (char_length(note) <= 1200),
    would_use_again boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (edit_run_id)
);

CREATE INDEX edit_feedback_job_updated_idx ON edit_feedback(job_id, updated_at DESC);
CREATE INDEX edit_feedback_updated_idx ON edit_feedback(updated_at DESC);
