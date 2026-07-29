-- Drop exhaustive mode CHECK; app validates against FnGuide modes + adhoc registry.
ALTER TABLE fnguide_crawls
    DROP CONSTRAINT IF EXISTS fnguide_crawls_mode_check;
