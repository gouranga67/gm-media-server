ALTER TABLE edit_feedback ADD COLUMN scope text NOT NULL DEFAULT 'edit' CHECK(scope IN ('edit','story','pacing','captions','audio','colour','effects'));
ALTER TABLE edit_feedback ADD COLUMN start_seconds double precision;
ALTER TABLE edit_feedback ADD COLUMN end_seconds double precision;
ALTER TABLE edit_feedback ADD CONSTRAINT edit_feedback_time_range CHECK (
    (start_seconds IS NULL AND end_seconds IS NULL) OR
    (start_seconds IS NOT NULL AND end_seconds IS NOT NULL AND start_seconds >= 0 AND end_seconds > start_seconds AND end_seconds <= 60)
);
CREATE TABLE learning_lessons (
    id uuid PRIMARY KEY,
    recipe text NOT NULL,
    edit_style text NOT NULL,
    rule_key text NOT NULL,
    directive text NOT NULL CHECK(length(directive) BETWEEN 1 AND 600),
    status text NOT NULL DEFAULT 'proposed' CHECK(status IN ('proposed','promoted','rolled_back')),
    training_feedback_ids jsonb NOT NULL,
    training_job_ids jsonb NOT NULL,
    training_source_hashes jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(recipe,edit_style,rule_key)
);
ALTER TABLE edit_runs ADD COLUMN evaluation_lesson_id uuid REFERENCES learning_lessons(id);
CREATE TABLE learning_evaluations (
    id uuid PRIMARY KEY,
    lesson_id uuid NOT NULL REFERENCES learning_lessons(id),
    job_id uuid NOT NULL REFERENCES jobs(id),
    baseline_run_id uuid NOT NULL REFERENCES edit_runs(id),
    candidate_run_id uuid NOT NULL REFERENCES edit_runs(id),
    baseline_rating integer NOT NULL CHECK(baseline_rating BETWEEN 1 AND 5),
    candidate_rating integer NOT NULL CHECK(candidate_rating BETWEEN 1 AND 5),
    note text NOT NULL DEFAULT '' CHECK(length(note)<=1200),
    reviewer text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(lesson_id,job_id),
    CHECK(baseline_run_id<>candidate_run_id)
);
ALTER TABLE edit_runs ADD COLUMN repair_kind text CHECK(repair_kind IN ('tighten_pauses','denoise'));
CREATE UNIQUE INDEX edit_runs_one_local_repair ON edit_runs(based_on_run_id) WHERE repair_kind IS NOT NULL;
