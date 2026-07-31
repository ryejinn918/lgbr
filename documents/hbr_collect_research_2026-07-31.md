# HBR.org 수집 조사 (2026-07-31)

영문 HBR (`https://hbr.org/`). 한글판 `hbrkorea`와 별도.  
아티팩트:
- 초기(구 계정 실패): `.crawler/snapshots/hbr-research/`
- v5 재검증(성공): `.crawler/snapshots/hbr-research-v5/`

## 로그인 UI

- `/signin` URL: **404** (Page Not Found)
- 확인된 로그인 UI: hub `#sign-in-button-header` → `[role=dialog]` 모달
  - `input[name="emailAddress"]`, `input[name="password"]`
  - `button[type=submit]` 텍스트 `Sign In` (입력 전에는 disabled)
  - invisible reCAPTCHA
- 실패 시 연타 금지 (사이트 rate-limit / 시도 제한)

## v5 계정 재검증 (2026-07-31 밤)

- 정기간행물 엑셀 v5 No.12와 `crawler/.env` `HBR_*` 동기화 (ID `rahakim@…`, 구 env `raha@…`·짧은 PW와 불일치였음)
- 클린 프로필 `browser-profile-hbr`로 hub → 모달 → **제출 1회만**
- **로그인 성공** — 헤더 `Hi, raha`, Sign In 버튼 소멸
- Latest (`/the-latest`) 아티클 링크 다수 확인
- 상세 1건: `…/2026/07/ai-and-it-teams-often-clash-but-they-dont-have-to`
  - 로그인 본문 확보, `page.pdf` ≈593KB, `pdftotext`로 Summary·본문 확인
- Piano가 DOM에 숨긴 `#paywall-creative-container`가 class 매칭 오탐 →  
  `hbr_browser.capture_article_pdf`에서 **보이는 paywall만** 차단하도록 수정
- 프로필 재오픈 시 세션 유지 확인 (재로그인 불필요)

## Hub / 네비

- Hub: `https://hbr.org/`
- Latest: `https://hbr.org/the-latest`
- Magazine: `https://hbr.org/magazine`
- 아티클 URL 형태: `https://hbr.org/{YYYY}/{MM}/{slug}`

## 자동화 절차

1. `HBR_*` env → hub Sign In 모달 로그인 (영속 프로필 `browser-profile-hbr`)
2. `https://hbr.org/the-latest` → 카드 수집 → UI에 `Load More Items` 있을 때만 클릭
3. **한 건씩** 상세 + delay
4. 보이는 paywall/짧은 본문이면 `no_download`; 충분하면 `page.pdf`
5. HTTP 목록/상세 연타 없음. 로그인 거절 시 재시도 금지

## 대기

- `wait_until=domcontentloaded`, 페이지 ~2–3.5s, 아이템 간 ≥4–5s

## Phase 상태

- Phase 1–3: 레지스트리·세션·브라우저 잡·FE 배선 완료
- Phase 4 애드혹 로그인·상세 1건·page.pdf: **완료** (v5)
- Phase 4 검색 스모크: **완료** — `search run --limit 3 --max-pages 2 --item-delay-seconds 5`
  - job `d5d99a9b-…`: `downloaded=3 listed=4 no_dl=1 failed=0`
  - asset `fn-hb-260731-4bced6` (page.pdf 3건, pdftotext 본문 확인)
  - `audit_report_quality.py --source hbr --limit 3` → pass=3 reject=0
