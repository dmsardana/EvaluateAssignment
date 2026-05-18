-- Initial schema for the EvaluateAssignment pipeline data layer.
-- Mirrors the three Drive-stored files this replaces:
--   scores.csv              -> scores table
--   students.csv            -> students table
--   answer_key_state.json   -> answer_key_state table
--
-- All three sit behind a single Drive→Postgres migration in
-- tools/db_migrate.py. PDFs themselves stay on Drive.
--
-- Primary keys + uniqueness constraints eliminate the read-modify-write
-- races we were patching around with threading.Lock in Python — the
-- database enforces invariants atomically, and `UPDATE`/`UPSERT` replace
-- "read whole file, mutate, write whole file" semantics.

CREATE TABLE IF NOT EXISTS students (
    student_id   TEXT PRIMARY KEY,
    student_name TEXT NOT NULL DEFAULT '',
    -- Personalised name the teacher sets — wins over student_name in
    -- email greetings + UI when non-empty.
    display_name TEXT,
    email        TEXT,
    mobile       TEXT,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS scores (
    assignment_type     TEXT NOT NULL,
    assignment_code     TEXT NOT NULL,
    student_id          TEXT NOT NULL,
    student_name        TEXT NOT NULL DEFAULT '',
    evaluation_date     DATE,
    total_questions     INTEGER,
    earned_score        NUMERIC(8,3),
    max_score           NUMERIC(6,1),
    percentage          NUMERIC(5,1),
    -- Per-dimension averages (concept_understanding, approach_method,
    -- step_by_step, numerical_accuracy, presentation) — kept as
    -- denormalised columns so the existing distribution view doesn't
    -- need an extra join.
    concept_pct         NUMERIC(5,1),
    approach_pct        NUMERIC(5,1),
    steps_pct           NUMERIC(5,1),
    accuracy_pct        NUMERIC(5,1),
    clarity_pct         NUMERIC(5,1),
    qualifies_for       TEXT,
    -- Port-back state for the Drive-share + Gmail flow.
    linked_at           TIMESTAMPTZ,
    unlinked_at         TIMESTAMPTZ,
    assigned_grade      NUMERIC(8,3),
    shared_with_email   TEXT,
    drive_permission_id TEXT,
    -- NEW vs scores.csv: stored directly instead of inferred via
    -- filename matching against the reports/ folder. Eliminates the
    -- ambiguous-PDF case where two reports with the same canonical
    -- filename existed on Drive.
    report_drive_id     TEXT,
    -- Stable join key — populated on every new grading row and backfilled
    -- for existing rows via tools/db_migrate.py --backfill-coursework-id.
    -- NULL on legacy rows that predate this column.
    coursework_id TEXT,
    PRIMARY KEY (assignment_type, assignment_code, student_id)
);

CREATE INDEX IF NOT EXISTS idx_scores_assignment
    ON scores (assignment_type, assignment_code);
-- Idempotent upgrade for databases created before this column was added.
ALTER TABLE scores ADD COLUMN IF NOT EXISTS coursework_id TEXT;
-- Per-evaluation timing — captured on the worker thread when the user
-- clicks "Evaluate" (eval_started_at) and again after the score is recorded
-- (eval_completed_at). Duration in seconds is derived in the API layer so
-- we don't have to keep a third column in sync.
ALTER TABLE scores ADD COLUMN IF NOT EXISTS eval_started_at   TIMESTAMPTZ;
ALTER TABLE scores ADD COLUMN IF NOT EXISTS eval_completed_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_scores_coursework
    ON scores (coursework_id);
CREATE INDEX IF NOT EXISTS idx_scores_student
    ON scores (student_id);
CREATE INDEX IF NOT EXISTS idx_scores_linked
    ON scores (linked_at, unlinked_at);

CREATE TABLE IF NOT EXISTS answer_key_state (
    coursework_id     TEXT PRIMARY KEY,
    course_id         TEXT NOT NULL,
    assignment_type   TEXT NOT NULL,
    assignment_code   TEXT NOT NULL,
    assignment_title  TEXT,
    -- DETECTED | GENERATING | PENDING_REVIEW | NEEDS_REGEN | APPROVED
    status            TEXT NOT NULL,
    current_otp       TEXT,
    model             TEXT,
    generated_at      TIMESTAMPTZ,
    approved_at       TIMESTAMPTZ,
    thread_id         TEXT,
    regen_count       INTEGER NOT NULL DEFAULT 0,
    drive_pdf_id      TEXT,
    -- The questions + per-question approval state live in JSONB so the
    -- schema doesn't need to change as the question shape evolves.
    questions         JSONB NOT NULL DEFAULT '[]'::jsonb,
    questions_status  JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_message     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_aks_status
    ON answer_key_state (status);

-- Auto-bump updated_at on every UPDATE so consumers can poll for change.
CREATE OR REPLACE FUNCTION _touch_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_aks_touch ON answer_key_state;
CREATE TRIGGER trg_aks_touch
    BEFORE UPDATE ON answer_key_state
    FOR EACH ROW EXECUTE FUNCTION _touch_updated_at();

DROP TRIGGER IF EXISTS trg_students_touch ON students;
CREATE TRIGGER trg_students_touch
    BEFORE UPDATE ON students
    FOR EACH ROW EXECUTE FUNCTION _touch_updated_at();

CREATE TABLE IF NOT EXISTS credentials_health (
    name                  TEXT PRIMARY KEY,
    status                TEXT NOT NULL,
    last_checked_at       TIMESTAMPTZ NOT NULL,
    last_ok_at            TIMESTAMPTZ,
    last_error            TEXT,
    recovery_started_at   TIMESTAMPTZ,
    notified_at           TIMESTAMPTZ,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_credentials_health_status
    ON credentials_health (status);
