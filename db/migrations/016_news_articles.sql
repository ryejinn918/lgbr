-- News articles from SerpAPI Google News (reports-style identity + query cache).

CREATE TABLE IF NOT EXISTS news_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    source_key TEXT NOT NULL,
    title TEXT NOT NULL,
    snippet TEXT,
    url TEXT NOT NULL,
    published_at TIMESTAMPTZ,
    publisher TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (source, source_key)
);

CREATE INDEX IF NOT EXISTS news_articles_published_idx
    ON news_articles (published_at DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS news_articles_publisher_idx
    ON news_articles (publisher);

CREATE INDEX IF NOT EXISTS news_articles_last_seen_idx
    ON news_articles (last_seen_at DESC);

CREATE TABLE IF NOT EXISTS news_search_queries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_norm TEXT NOT NULL UNIQUE,
    query_raw TEXT NOT NULL,
    engine TEXT NOT NULL DEFAULT 'google_news',
    last_searched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    hit_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS news_search_hits (
    query_id UUID NOT NULL REFERENCES news_search_queries (id) ON DELETE CASCADE,
    article_id UUID NOT NULL REFERENCES news_articles (id) ON DELETE CASCADE,
    rank INTEGER NOT NULL DEFAULT 0,
    searched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (query_id, article_id)
);

CREATE INDEX IF NOT EXISTS news_search_hits_article_idx
    ON news_search_hits (article_id);
