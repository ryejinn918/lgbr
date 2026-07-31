# Bain & Company 수집 조사 (2026-07-31)

무계정 Patchright 세션. 아티팩트: `.crawler/snapshots/bain-research/` (`findings.json`, 스크린샷, `report-sample.pdf`, `article-page.pdf`).

HTTP 목록/상세 연타·API 추정 없음. 확인된 UI 경로만 기록.

## Hub

- URL: `https://www.bain.com/`
- 타이틀: Global Management Consulting Firm | Bain & Company
- Access Denied / 로그인월: **없음** (`body_len` ~3000)
- 쿠키: 화면에 Accept 버튼 보이면 클릭 (`button:has-text('Accept')` / `#onetrust-accept-btn-handler`)
- 네비 `Insights`는 `href=#` 메가메뉴. 실제 목록은 아래 Insights 허브로 이동해 확인.

## 목록

- URL: `https://www.bain.com/insights/` (타이틀: Bain Insights & Publications)
- Access Denied: **없음**
- 카드(확인):
  - 피드: `div.feed__results-container` 안 `div.card.card--insights` / `div.card__wrapper[data-url]`
  - 리스트 보조: `ul.insights-list__list li` → `div.insights-list__text-container` + `h4 a[href*="/insights/"]`
  - 사이트 검색 제안(`.site-search__…`) 링크는 **제외**
- 날짜: 카드 안 `span.date-format` (예: `Jun 29, 2026`)
- 유형 텍스트: `Brief` / `Report` 등 (`p.insights-list__content-type` 또는 카드 본문)
- 아티클 URL 형태: `https://www.bain.com/insights/{slug}/` (카테고리 허브 `industry-insights` 등은 제외)
- 페이지네이션: 스크롤 후 **`a.btn.btn--cta` 텍스트 `LOAD MORE`** 클릭 1회 → 고유 아티클 링크 수 증가 확인(예: → 38). “Next page” URL 패턴은 UI에서 확인하지 않음.

## 상세 (1~2건)

1. Brief `…/insights/proprietary-intelligence-how-to-win-with-ai/`
   - `main` ~13k자, Access Denied/로그인월 **없음**
   - `a[href*=".pdf"]` **없음**
   - `page.pdf` 저장 성공(~1.7MB). `pdftotext`에 Access Denied 없음(텍스트 레이어는 얇음 — 본문은 HTML에 존재)
2. Report `…/insights/private-equity-midyear-report-2026/`
   - `main` ~22k자, 차단 없음
   - PDF 링크 확인: `https://www.bain.com/globalassets/noindex/2026/bain-report_private-equity-midyear-report-2026.pdf`
   - **같은 브라우저** `context.request.get` 1회: HTTP 200, `application/pdf`, ~2.4MB, `pdftotext`에 본문·Access Denied 없음

## 자동화에 쓸 절차 (추정 API 없음)

1. 영속 프로필 워밍업 → (선택) hub → 쿠키 수락(있을 때만) → `https://www.bain.com/insights/`
2. `main`에서 `.site-search` 제외한 카드 수집; 날짜는 `span.date-format`
3. UI에 `LOAD MORE` 있을 때만 클릭해 페이지 확장
4. **한 건씩** 상세 `goto` + 아이템 delay
5. 상세에 `.pdf` 링크 있으면 브라우저 컨텍스트로 1파일 저장; 없으면 Access Denied/본문 길이 게이트 후 `page.pdf`
6. Access Denied·빈 본문·거부 PDF는 `downloaded`로 치지 않음

## 대기

- `wait_until=domcontentloaded`
- 페이지 안정화 ~2.5–3.5s, 아이템 간 ≥4–5s (연타 금지)
