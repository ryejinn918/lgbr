-- Expand existing FnGuide profiles without adding new top-level sectors.
-- Energy, healthcare/bio, telecom, and strategy/HR remain out of scope here.

UPDATE search_profiles
SET keywords = ARRAY[
    'AI', 'AI 반도체', '생성형 AI', 'LLM',
    'AIDC', '데이터센터', 'AI Semiconductor', 'AI Chip',
    '피지컬 AI', 'Physical AI', '휴머노이드', 'Humanoid',
    '로보틱스', 'Robotics'
], updated_at = now()
WHERE mode = 'ai';

UPDATE search_profiles
SET keywords = ARRAY[
    '가전 산업', '가전 시장', '가전 업황', '가전 전망',
    '백색가전 시장', 'HVAC 시장',
    '스마트홈', '가전', '백색가전', 'TV', '냉장고', '세탁기',
    '건조기', '청소기', '로봇청소기', '로청', '식세기',
    '에어컨', '공조', 'HVAC'
], updated_at = now()
WHERE mode = 'appliance';

UPDATE search_profiles
SET keywords = ARRAY[
    '디스플레이 산업', '디스플레이 시장', '디스플레이 업황',
    '디스플레이 전망', 'OLED 산업', '패널 가격',
    '패널', '디스플레이', 'OLED'
], updated_at = now()
WHERE mode = 'display';

UPDATE search_profiles
SET keywords = ARRAY[
    '자동차', '전장', '전기차', '모빌리티', 'ESS', 'EV',
    '배터리', 'LFP', 'NCM', 'SDV', 'ADV'
], updated_at = now()
WHERE mode = 'automotive';

UPDATE search_profiles
SET keywords = ARRAY[
    '석유화학', '석화', '화학', '케미칼', 'Chemicals', '납사'
], updated_at = now()
WHERE mode = 'petrochemical';

UPDATE search_profiles
SET keywords = ARRAY[
    '거시경제 전망', '경제 전망', '금리 전망', '환율 전망',
    '자산배분 전략', '주식시장 전망',
    '거시경제', '매크로', '지정학'
], updated_at = now()
WHERE mode = 'macroeconomy';
