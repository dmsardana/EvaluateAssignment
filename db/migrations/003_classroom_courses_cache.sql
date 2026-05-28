-- db/migrations/003_classroom_courses_cache.sql
-- Read-through cache for Google Classroom course list. Populated by the
-- /api/classrooms endpoint with a 5-minute TTL so the queue-page dropdown
-- doesn't have to wait for /api/queue (which makes N+M Google API round
-- trips for courseworks + submission counts).
-- Apply with:
--   docker exec -i evalassign-db psql -U evalassign -d evalassign \
--     < db/migrations/003_classroom_courses_cache.sql
-- Idempotent.

CREATE TABLE IF NOT EXISTS classroom_courses (
    course_id   TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    section     TEXT NOT NULL DEFAULT '',
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Staleness probe: SELECT max(fetched_at) FROM classroom_courses.
-- If older than TTL the service refreshes via courses().list() and upserts.
