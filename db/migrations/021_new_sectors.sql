-- New search/consensus modes + keyword list refresh for ai / physical_ai.
ALTER TABLE fnguide_crawls
    DROP CONSTRAINT IF EXISTS fnguide_crawls_mode_check;

ALTER TABLE fnguide_crawls
    ADD CONSTRAINT fnguide_crawls_mode_check
    CHECK (mode IN (
        'auto',
        'adhoc',
        'datacenter',
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
        'datacenter',
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
        'datacenter',
        'ai',
        'physical_ai',
        'appliance',
        'display',
        'automotive',
        'petrochemical'
    ));

UPDATE search_profiles
SET
    keywords = ARRAY['AI', 'AIDC', '데이터센터', 'AI 반도체'],
    updated_at = now()
WHERE mode = 'ai';

UPDATE search_profiles
SET
    keywords = ARRAY[
        '피지컬 AI',
        'Physical AI',
        '휴머노이드',
        'Humanoid',
        '로보틱스',
        '로봇',
        '온디바이스 칩'
    ],
    updated_at = now()
WHERE mode = 'physical_ai';

INSERT INTO search_profiles (mode, keywords, sectors, period_months, page_min_label)
VALUES
    (
        'appliance',
        ARRAY[
            '가전',
            '백색가전',
            'TV',
            '냉장고',
            '세탁기',
            '청소기',
            '에어컨',
            '디바이스',
            '공조',
            'HVAC'
        ],
        ARRAY[]::TEXT[],
        3,
        '10p 이상'
    ),
    (
        'display',
        ARRAY['디스플레이', '패널', 'OLED'],
        ARRAY[]::TEXT[],
        3,
        '10p 이상'
    ),
    (
        'automotive',
        ARRAY[
            '자동차',
            '전장',
            '전기차',
            '모빌리티',
            'ESS',
            'EV',
            '배터리',
            'LFP',
            'NCM',
            'SDV',
            'ADV'
        ],
        ARRAY[]::TEXT[],
        3,
        '10p 이상'
    ),
    (
        'petrochemical',
        ARRAY[
            '석유화학',
            '석화',
            '화학',
            '케미칼',
            'Chemicals',
            '납사'
        ],
        ARRAY[]::TEXT[],
        3,
        '10p 이상'
    )
ON CONFLICT (mode) DO NOTHING;
