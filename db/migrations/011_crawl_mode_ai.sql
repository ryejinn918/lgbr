-- Allow mode=ai for SearchReport AI profile crawls.
ALTER TABLE fnguide_crawls
    DROP CONSTRAINT IF EXISTS fnguide_crawls_mode_check;

ALTER TABLE fnguide_crawls
    ADD CONSTRAINT fnguide_crawls_mode_check
    CHECK (mode IN ('auto', 'adhoc', 'datacenter', 'ai'));
