-- Body fill fields for news_articles (ARG fetch_body, etc.)

ALTER TABLE news_articles
    ADD COLUMN IF NOT EXISTS body_text TEXT,
    ADD COLUMN IF NOT EXISTS body_fetched_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS body_fetch_error TEXT;

CREATE INDEX IF NOT EXISTS news_articles_pending_body_idx
    ON news_articles (source, published_at DESC NULLS LAST)
    WHERE body_text IS NULL;
