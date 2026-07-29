-- Restore datacenter crawl profile; expand consensus themes with datacenter + macroeconomy.
-- Report content themes live in attrs.themes[]; crawl tag in attrs.crawl_profile.

-- 1) search_profiles: allow datacenter again
ALTER TABLE search_profiles
    DROP CONSTRAINT IF EXISTS search_profiles_mode_check;

ALTER TABLE search_profiles
    ADD CONSTRAINT search_profiles_mode_check
    CHECK (mode IN (
        'ai',
        'datacenter',
        'physical_ai',
        'appliance',
        'display',
        'automotive',
        'petrochemical'
    ));

-- AI: model/infra software focus (no AIDC / data-center keywords)
UPDATE search_profiles
SET
    keywords = ARRAY['AI', 'AI 반도체', '생성형 AI', 'LLM'],
    sectors = ARRAY[
        'IT',
        '커뮤니케이션서비스',
        '금융'
    ],
    updated_at = now()
WHERE mode = 'ai';

INSERT INTO search_profiles (mode, keywords, sectors, period_months, page_min_label)
VALUES (
    'datacenter',
    ARRAY['데이터센터', 'AIDC', 'AI 데이터센터', '전력', '냉각'],
    ARRAY[
        '에너지',
        '소재',
        '산업재',
        '유틸리티',
        'IT'
    ],
    3,
    '10p 이상'
)
ON CONFLICT (mode) DO UPDATE SET
    keywords = EXCLUDED.keywords,
    sectors = EXCLUDED.sectors,
    period_months = EXCLUDED.period_months,
    page_min_label = EXCLUDED.page_min_label,
    updated_at = now();

-- 2) consensus_runs theme CHECK
ALTER TABLE consensus_runs
    DROP CONSTRAINT IF EXISTS consensus_runs_theme_check;

ALTER TABLE consensus_runs
    ADD CONSTRAINT consensus_runs_theme_check
    CHECK (theme IN (
        'ai',
        'datacenter',
        'macroeconomy',
        'physical_ai',
        'appliance',
        'display',
        'automotive',
        'petrochemical'
    ));

-- 3) Backfill crawl_profile from legacy attrs.theme (do not invent themes[])
UPDATE reports
SET attrs = attrs || jsonb_build_object('crawl_profile', attrs->>'theme')
WHERE attrs->>'theme' IS NOT NULL
  AND (attrs->>'crawl_profile' IS NULL OR attrs->>'crawl_profile' = '');

-- Note: fnguide_crawls.mode CHECK was dropped in 027 (app-validated).
