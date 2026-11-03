CREATE TABLE learning_cases (
    id uuid PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES jobs(id),
    baseline_run_id uuid NOT NULL REFERENCES edit_runs(id),
    label text NOT NULL CHECK (length(label) BETWEEN 1 AND 120),
    recording_group text NOT NULL CHECK (length(recording_group) BETWEEN 1 AND 120),
    category text NOT NULL CHECK (category IN ('story', 'speech', 'captions', 'visuals', 'audio', 'effects')),
    expectations text NOT NULL CHECK (length(expectations) BETWEEN 1 AND 1200),
    max_candidate_tokens integer CHECK (max_candidate_tokens BETWEEN 1 AND 2000000),
    snapshot jsonb NOT NULL CHECK (jsonb_typeof(snapshot) = 'object'),
    snapshot_hash text NOT NULL CHECK (snapshot_hash ~ '^[0-9a-f]{64}$'),
    created_by text NOT NULL,
    archived_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(baseline_run_id)
);
ALTER TABLE edit_runs ADD COLUMN evaluation_case_id uuid REFERENCES learning_cases(id);
ALTER TABLE learning_lessons ADD COLUMN evaluation_protocol integer NOT NULL DEFAULT 1 CHECK (evaluation_protocol IN (1,2));
ALTER TABLE learning_lessons ALTER COLUMN evaluation_protocol SET DEFAULT 2;
ALTER TABLE learning_lessons ADD COLUMN deployment_version integer NOT NULL DEFAULT 0 CHECK (deployment_version >= 0);
CREATE TABLE learning_lesson_events (
    id uuid PRIMARY KEY,
    lesson_id uuid NOT NULL REFERENCES learning_lessons(id),
    deployment_version integer NOT NULL CHECK (deployment_version > 0),
    action text NOT NULL CHECK (action IN ('promote', 'rollback', 'upgrade')),
    previous_status text NOT NULL,
    status text NOT NULL,
    directive_hash text NOT NULL CHECK (directive_hash ~ '^[0-9a-f]{64}$'),
    actor text NOT NULL,
    evaluation jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(lesson_id, deployment_version)
);
