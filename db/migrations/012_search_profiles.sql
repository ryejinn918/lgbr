-- Editable SearchReport filter profiles for fixed modes (datacenter, ai).
CREATE TABLE IF NOT EXISTS search_profiles (
    mode TEXT PRIMARY KEY CHECK (mode IN ('datacenter', 'ai')),
    keyword TEXT NOT NULL,
    sectors TEXT[] NOT NULL DEFAULT '{}',
    period_months INT NOT NULL DEFAULT 3 CHECK (period_months IN (3, 6, 12)),
    page_min_label TEXT NOT NULL DEFAULT '10p 이상',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO search_profiles (mode, keyword, sectors, period_months, page_min_label)
VALUES
    (
        'datacenter',
        '데이터센터',
        ARRAY[
            '에너지',
            '소재',
            '산업재',
            '금융',
            'IT',
            '커뮤니케이션서비스',
            '유틸리티'
        ],
        3,
        '10p 이상'
    ),
    (
        'ai',
        'AI',
        ARRAY[]::TEXT[],
        3,
        '10p 이상'
    )
ON CONFLICT (mode) DO NOTHING;
