-- Source-agnostic collection jobs (list expansion / body fill).
-- Separate from fnguide_crawls (browser session crawls).

CREATE TABLE IF NOT EXISTS collection_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    capability TEXT NOT NULL
        CHECK (capability IN ('feed', 'search', 'fetch_body', 'download')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    stop_requested_at TIMESTAMPTZ,
    pid INTEGER,
    state TEXT NOT NULL
        CHECK (state IN ('starting', 'active', 'stopping', 'ended', 'error')),
    progress JSONB NOT NULL DEFAULT '{}'::jsonb,
    message TEXT
);

CREATE INDEX IF NOT EXISTS collection_jobs_open_idx
    ON collection_jobs (started_at DESC)
    WHERE ended_at IS NULL;

CREATE INDEX IF NOT EXISTS collection_jobs_history_idx
    ON collection_jobs (started_at DESC);

CREATE INDEX IF NOT EXISTS collection_jobs_source_idx
    ON collection_jobs (source, capability, started_at DESC);

-- At most one open job per (source, capability).
CREATE UNIQUE INDEX IF NOT EXISTS collection_jobs_one_open_uidx
    ON collection_jobs (source, capability)
    WHERE ended_at IS NULL;

CREATE INDEX IF NOT EXISTS news_articles_source_last_seen_idx
    ON news_articles (source, last_seen_at DESC);
