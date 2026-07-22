-- Fail-closed: crawl may end in error; at most one open crawl/session.
ALTER TABLE fnguide_crawls
    DROP CONSTRAINT IF EXISTS fnguide_crawls_state_check;

ALTER TABLE fnguide_crawls
    ADD CONSTRAINT fnguide_crawls_state_check
    CHECK (state IN ('starting', 'active', 'stopping', 'ended', 'error'));

-- Only one non-terminal crawl at a time.
CREATE UNIQUE INDEX IF NOT EXISTS fnguide_crawls_one_open_uidx
    ON fnguide_crawls ((true))
    WHERE ended_at IS NULL;

-- Only one open account session at a time.
CREATE UNIQUE INDEX IF NOT EXISTS fnguide_sessions_one_open_uidx
    ON fnguide_sessions ((true))
    WHERE ended_at IS NULL;
