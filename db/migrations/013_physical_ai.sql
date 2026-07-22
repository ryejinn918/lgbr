-- Allow mode=physical_ai and seed its search profile.
ALTER TABLE fnguide_crawls
    DROP CONSTRAINT IF EXISTS fnguide_crawls_mode_check;

ALTER TABLE fnguide_crawls
    ADD CONSTRAINT fnguide_crawls_mode_check
    CHECK (mode IN ('auto', 'adhoc', 'datacenter', 'ai', 'physical_ai'));

ALTER TABLE search_profiles
    DROP CONSTRAINT IF EXISTS search_profiles_mode_check;

ALTER TABLE search_profiles
    ADD CONSTRAINT search_profiles_mode_check
    CHECK (mode IN ('datacenter', 'ai', 'physical_ai'));

INSERT INTO search_profiles (mode, keyword, sectors, period_months, page_min_label)
VALUES (
    'physical_ai',
    '피지컬',
    ARRAY[]::TEXT[],
    12,
    '전체'
)
ON CONFLICT (mode) DO NOTHING;
