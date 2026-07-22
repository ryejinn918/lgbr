-- Crawl runs (parent); account session is a subtask linked by session_id
CREATE TABLE IF NOT EXISTS fnguide_crawls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES fnguide_sessions (id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    stop_requested_at TIMESTAMPTZ,
    pid INTEGER,
    state TEXT NOT NULL
        CHECK (state IN ('starting', 'active', 'stopping', 'ended')),
    message TEXT
);

CREATE INDEX IF NOT EXISTS fnguide_crawls_open_idx
    ON fnguide_crawls (started_at DESC)
    WHERE ended_at IS NULL;

CREATE INDEX IF NOT EXISTS fnguide_crawls_history_idx
    ON fnguide_crawls (started_at DESC);
