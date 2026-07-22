-- Fnguide account session + event history
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS fnguide_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fnguide_user_id TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    lease_until TIMESTAMPTZ,
    logout_requested_at TIMESTAMPTZ,
    pid INTEGER,
    current_url TEXT,
    step TEXT,
    message TEXT,
    state TEXT NOT NULL
        CHECK (state IN ('logging_in', 'logged_in', 'logging_out', 'ended', 'error')),
    end_reason TEXT
        CHECK (
            end_reason IS NULL
            OR end_reason IN ('manual', 'idle', 'ttl', 'external', 'error', 'shutdown')
        )
);

CREATE INDEX IF NOT EXISTS fnguide_sessions_open_idx
    ON fnguide_sessions (started_at DESC)
    WHERE ended_at IS NULL;

CREATE INDEX IF NOT EXISTS fnguide_sessions_history_idx
    ON fnguide_sessions (started_at DESC);

CREATE TABLE IF NOT EXISTS fnguide_session_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES fnguide_sessions (id) ON DELETE CASCADE,
    at TIMESTAMPTZ NOT NULL DEFAULT now(),
    event TEXT NOT NULL
        CHECK (
            event IN (
                'login_start',
                'login_ok',
                'login_fail',
                'touch',
                'logout_request',
                'logout_ok',
                'external_logout',
                'error'
            )
        ),
    detail JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS fnguide_session_events_session_idx
    ON fnguide_session_events (session_id, at DESC);
