-- Search crawls use profile period (not report count). report_limit NULL = no count cap.
ALTER TABLE fnguide_crawls
    DROP CONSTRAINT IF EXISTS fnguide_crawls_report_limit_check;

ALTER TABLE fnguide_crawls
    ALTER COLUMN report_limit DROP NOT NULL;

ALTER TABLE fnguide_crawls
    ALTER COLUMN report_limit DROP DEFAULT;

ALTER TABLE fnguide_crawls
    ADD CONSTRAINT fnguide_crawls_report_limit_check
    CHECK (report_limit IS NULL OR (report_limit >= 1 AND report_limit <= 50));

ALTER TABLE fnguide_crawls
    ADD COLUMN IF NOT EXISTS period_months INTEGER;

ALTER TABLE fnguide_crawls
    DROP CONSTRAINT IF EXISTS fnguide_crawls_period_months_check;

ALTER TABLE fnguide_crawls
    ADD CONSTRAINT fnguide_crawls_period_months_check
    CHECK (period_months IS NULL OR period_months IN (3, 6, 12));
