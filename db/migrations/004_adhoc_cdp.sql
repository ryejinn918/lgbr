-- Adhoc crawl mode + CDP remote debugging port
ALTER TABLE fnguide_crawls
    ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'auto';

ALTER TABLE fnguide_crawls
    DROP CONSTRAINT IF EXISTS fnguide_crawls_mode_check;

ALTER TABLE fnguide_crawls
    ADD CONSTRAINT fnguide_crawls_mode_check
    CHECK (mode IN ('auto', 'adhoc'));

ALTER TABLE fnguide_crawls
    ADD COLUMN IF NOT EXISTS cdp_port INTEGER;
