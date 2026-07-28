-- Merge datacenter into ai (AI/AIDC). No consensus re-run; remap tags only.

-- 1) AI search profile absorbs former datacenter sectors; drop datacenter profile.
UPDATE search_profiles
SET
    keywords = ARRAY['AI', 'AIDC', '데이터센터', 'AI 반도체'],
    sectors = ARRAY[
        '에너지',
        '소재',
        '산업재',
        '금융',
        'IT',
        '커뮤니케이션서비스',
        '유틸리티'
    ],
    updated_at = now()
WHERE mode = 'ai';

DELETE FROM search_profiles WHERE mode = 'datacenter';

-- 2) Report theme tags.
UPDATE reports
SET attrs = jsonb_set(attrs, '{theme}', '"ai"', true)
WHERE attrs->>'theme' = 'datacenter';

-- 3) Consensus history under AI/AIDC (outputs unchanged).
UPDATE consensus_runs
SET theme = 'ai'
WHERE theme = 'datacenter';

-- 4) Crawl history mode labels.
UPDATE fnguide_crawls
SET mode = 'ai'
WHERE mode = 'datacenter';

-- 5) Tighten CHECKs (datacenter removed from active modes).
ALTER TABLE fnguide_crawls
    DROP CONSTRAINT IF EXISTS fnguide_crawls_mode_check;

ALTER TABLE fnguide_crawls
    ADD CONSTRAINT fnguide_crawls_mode_check
    CHECK (mode IN (
        'auto',
        'adhoc',
        'ai',
        'physical_ai',
        'appliance',
        'display',
        'automotive',
        'petrochemical'
    ));

ALTER TABLE search_profiles
    DROP CONSTRAINT IF EXISTS search_profiles_mode_check;

ALTER TABLE search_profiles
    ADD CONSTRAINT search_profiles_mode_check
    CHECK (mode IN (
        'ai',
        'physical_ai',
        'appliance',
        'display',
        'automotive',
        'petrochemical'
    ));

ALTER TABLE consensus_runs
    DROP CONSTRAINT IF EXISTS consensus_runs_theme_check;

ALTER TABLE consensus_runs
    ADD CONSTRAINT consensus_runs_theme_check
    CHECK (theme IN (
        'ai',
        'physical_ai',
        'appliance',
        'display',
        'automotive',
        'petrochemical'
    ));
