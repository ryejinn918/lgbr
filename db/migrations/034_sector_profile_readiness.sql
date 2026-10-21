-- Make every consensus theme collectable and bias sparse themes toward sector notes.
ALTER TABLE search_profiles
    DROP CONSTRAINT IF EXISTS search_profiles_mode_check;

ALTER TABLE search_profiles
    ADD CONSTRAINT search_profiles_mode_check
    CHECK (mode IN (
        'ai',
        'datacenter',
        'macroeconomy',
        'physical_ai',
        'appliance',
        'display',
        'automotive',
        'petrochemical'
    ));

INSERT INTO search_profiles (mode, keywords, sectors, period_months, page_min_label)
VALUES (
    'macroeconomy',
    ARRAY[
        '거시경제 전망',
        '경제 전망',
        '금리 전망',
        '환율 전망',
        '자산배분 전략',
        '주식시장 전망'
    ],
    ARRAY['금융'],
    3,
    '10p 이상'
)
ON CONFLICT (mode) DO UPDATE SET
    keywords = EXCLUDED.keywords,
    sectors = EXCLUDED.sectors,
    updated_at = now();

UPDATE search_profiles
SET
    keywords = ARRAY[
        '가전 산업',
        '가전 시장',
        '가전 업황',
        '가전 전망',
        '백색가전 시장',
        'HVAC 시장'
    ],
    sectors = ARRAY['경기소비재'],
    updated_at = now()
WHERE mode = 'appliance';

UPDATE search_profiles
SET
    keywords = ARRAY[
        '디스플레이 산업',
        '디스플레이 시장',
        '디스플레이 업황',
        '디스플레이 전망',
        'OLED 산업',
        '패널 가격'
    ],
    sectors = ARRAY['IT'],
    updated_at = now()
WHERE mode = 'display';