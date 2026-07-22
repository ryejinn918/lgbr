-- Generic downloaded report metadata (typed cols + source-specific attrs)
CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    source_key TEXT NOT NULL,
    crawl_id UUID REFERENCES fnguide_crawls (id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    author TEXT,
    published_at DATE,
    page_count INTEGER,
    file_path TEXT,
    file_name TEXT,
    downloaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (source, source_key)
);

CREATE INDEX IF NOT EXISTS reports_source_key_idx
    ON reports (source, source_key);

CREATE INDEX IF NOT EXISTS reports_crawl_idx
    ON reports (crawl_id);

CREATE INDEX IF NOT EXISTS reports_downloaded_idx
    ON reports (downloaded_at DESC);
