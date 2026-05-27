-- db/migrations/002_report_view_settings.sql
-- Per-tier report component selection. Overrides DEFAULT_VIEWS in
-- tools/report_view_config.py at runtime; falls back to defaults when
-- no row exists for a tier or when the DB is unreachable.
-- Apply with:
--   docker exec -i evalassign-db psql -U evalassign -d evalassign \
--     < db/migrations/002_report_view_settings.sql
-- Idempotent — safe to re-run.

CREATE TABLE IF NOT EXISTS report_view_settings (
    tier        TEXT PRIMARY KEY,
    components  JSONB NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
