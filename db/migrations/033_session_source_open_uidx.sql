-- Per-source open session lock (was global one-open).
ALTER TABLE fnguide_sessions
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'fnguide';

DROP INDEX IF EXISTS fnguide_sessions_one_open_uidx;

CREATE UNIQUE INDEX fnguide_sessions_one_open_uidx
    ON fnguide_sessions (source)
    WHERE ended_at IS NULL;

CREATE INDEX IF NOT EXISTS fnguide_sessions_source_history_idx
    ON fnguide_sessions (source, started_at DESC);
