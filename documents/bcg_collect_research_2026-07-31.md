# BCG 수집 조사 (2026-07-31)

무계정 Patchright. 아티팩트: `.crawler/snapshots/bcg-research/` (`findings.json`, 스크린샷, `detail-1.pdf`, `detail-2.pdf`).

HTTP/API 추정·연타 없음. 확인된 UI 경로만 기록.

## Hub

- URL: `https://www.bcg.com/`
- 타이틀: Strategic Management Consulting | Boston Consulting Group
- Access Denied / 로그인월: **없음** (`body_len` ~4.7k)
- 쿠키: `#onetrust-accept-btn-handler` / Accept (보이면)
- 네비: **Our Insights** → 메가메뉴 → **Featured Insights**의 **Visit Page**
  - Visit Page `href` 확인: `https://www.bcg.com/publications`
  - (텍스트만 `Featured Insights`인 `javascript:void(0)` 링크는 제외)

## 목록 (확인)

- URL: `https://www.bcg.com/publications`
- 타이틀/h1: Featured Insights and Perspectives | BCG
- Access Denied: **없음** (`body_len` ~5.6k)
- 카드: `a[href*="/publications/"]` 중 경로 `/publications/{YYYY}/{slug}`
  - 예: `https://www.bcg.com/publications/2026/building-business-value-with-ai-investment`
  - 제목 텍스트 길이 ≥12
- 날짜: 카드 근처 `JULY 31, 2026` 형태 (월 풀네임 + 일, 연)
- 첫 화면 카드 수: **6** (스크롤/Load More UI는 **미확인** — `Load More` 라벨 없음)

## 상세 (2건 — 성공)

같은 브라우저, 목록 클릭 또는 `goto`+Referer, 상세 사이 delay 5s.

1. `…/publications/2026/building-business-value-with-ai-investment`
   - `main` ~5.1k자, 차단 없음
   - PDF: `https://web-assets.bcg.com/pdf-src/prod-live/building-business-value-with-ai-investment.pdf`
   - `context.request` 1회: ~1.3MB, `%PDF`, `pdftotext`에 Access Denied 없음
2. `…/publications/2026/closing-the-leadership-belief-gap`
   - `main` ~12k자, 차단 없음
   - PDF: `https://web-assets.bcg.com/pdf-src/prod-live/closing-the-leadership-belief-gap.pdf`
   - ~2.9MB, `pdftotext` 본문 확인, Access Denied 없음

## 자동화에 쓸 절차 (다음 플랜용)

1. 영속 프로필 워밍업 → hub → 쿠키 → (가능하면) Our Insights 메뉴 → Visit Page로 `https://www.bcg.com/publications` (또는 동일 URL `goto`)
2. 카드 수집: `/publications/{year}/{slug}` + 날짜·제목
3. Load More가 UI에 생기면 그때만 클릭
4. **한 건씩** 상세 + delay ≥5s
5. 상세 `.pdf` 링크(주로 `web-assets.bcg.com`)면 브라우저 컨텍스트로 저장; 없으면 게이트된 `page.pdf`
6. Access Denied·빈 본문·거부 PDF는 `downloaded`로 치지 않음

## 현재 상태

- 수집 잡: `bcg_browser` + `bcg_report` (Bain형 1건씩, 프로필 `browser-profile-bcg-search`)
- FE: `hasSearch` + `BcgRunPage` / Dashboard 검색 카드 / Docs `reports/bcg`
