-- Operational crawl progress + append-only events (job-agnostic)
ALTER TABLE fnguide_crawls
    ADD COLUMN IF NOT EXISTS progress JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS fnguide_crawl_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crawl_id UUID NOT NULL REFERENCES fnguide_crawls (id) ON DELETE CASCADE,
    at TIMESTAMPTZ NOT NULL DEFAULT now(),
    level TEXT NOT NULL DEFAULT 'info'
        CHECK (level IN ('debug', 'info', 'warn', 'error')),
    stage TEXT NOT NULL DEFAULT '',
    event TEXT NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS fnguide_crawl_events_crawl_idx
    ON fnguide_crawl_events (crawl_id, at DESC);

CREATE INDEX IF NOT EXISTS fnguide_crawl_events_stage_idx
    ON fnguide_crawl_events (crawl_id, stage, at DESC);
