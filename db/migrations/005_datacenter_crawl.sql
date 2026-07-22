-- Datacenter crawl mode + report download limit
ALTER TABLE fnguide_crawls
    DROP CONSTRAINT IF EXISTS fnguide_crawls_mode_check;

ALTER TABLE fnguide_crawls
    ADD CONSTRAINT fnguide_crawls_mode_check
    CHECK (mode IN ('auto', 'adhoc', 'datacenter'));

ALTER TABLE fnguide_crawls
    ADD COLUMN IF NOT EXISTS report_limit INTEGER NOT NULL DEFAULT 5;

ALTER TABLE fnguide_crawls
    DROP CONSTRAINT IF EXISTS fnguide_crawls_report_limit_check;

ALTER TABLE fnguide_crawls
    ADD CONSTRAINT fnguide_crawls_report_limit_check
    CHECK (report_limit >= 1 AND report_limit <= 50);
