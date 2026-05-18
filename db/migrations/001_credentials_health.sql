-- db/migrations/001_credentials_health.sql
-- Apply with:
--   docker exec -i evalassign-db psql -U evalassign -d evalassign < db/migrations/001_credentials_health.sql
-- Idempotent — safe to re-run.

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
