# McKinsey 수집 조사 (2026-07-31) — Bain식 재조사

무계정 Patchright. 아티팩트: `.crawler/snapshots/mckinsey-research/`.  
HTTP/API 추정·연타 없음. **상세 Access Denied가 재현되면 추가 프로브 중단.**

## Hub

- URL: `https://www.mckinsey.com/`
- 타이틀: Global management consulting | McKinsey & Company
- 쿠키: `#onetrust-accept-btn-handler`
- Access Denied: **목록용 워밍업 프로필에서는 없음** (body ~2k)
- 네비 확인: **Our Insights** → `https://www.mckinsey.com/featured-insights`

## 목록 (확인)

- URL: `https://www.mckinsey.com/featured-insights` (h1: Our Insights)
- Access Denied: **없음** (body ~6–7k)
- 카드: `a[href*="/our-insights/"]` / `a[href*="/our-research/"]` + 제목 텍스트
  - 컨테이너 힌트: `GenericItem_mck-c-generic-item__content__…`
- 날짜: 카드 근처 `July 28, 2026` 형태
- URL 예: `…/capabilities/.../our-insights/{slug}`, `…/mgi/our-research/{slug}`
- 페이지네이션: 스크롤 후에도 **Load More / Next UI를 확인하지 못함** (첫 화면 ~10건)

## 상세 (차단 재현 — 성공 아님)

같은 브라우저에서 목록 → 상세(클릭 / `goto`+Referer) **모두 Access Denied**:

- 타이틀 `Access Denied`, edgesuite Reference #
- `page.pdf` / PDF 다운로드 **시도하지 않음** (차단 페이지를 downloaded로 치지 않음)
- 새 프로필로 hub를 다시 열면 hub조차 Denied가 날 수 있음 → **복구 연타 금지**

## 자동화에 쓸 절차 (상세 차단이 풀린 뒤)

1. 영속 프로필 `browser-profile-mckinsey-search` 워밍업 → 쿠키 → `featured-insights`
2. 카드 수집(날짜·제목·URL). Load More가 UI에 생기면 그때만 클릭
3. **한 건씩** 상세(가능하면 목록에서 클릭 우선) + delay ≥5s
4. 본문에 Access Denied면 즉시 `no_download` (page.pdf 폴백 금지)
5. 본문 충분 + PDF 링크면 브라우저 컨텍스트로 저장; 없으면 게이트된 `page.pdf`

## 현재 상태

- 목록 레인은 가능, **아티클 본문 수집은 엣지 차단으로 불가**
- 수집 잡: `mckinsey_browser` + `mckinsey_report` (Bain형 1건씩, Access Denied → `no_download`, 연속 2회 Denied면 `access_denied_streak` 중단)
- FE: `hasSearch` + `MckinseyRunPage` / Dashboard 검색 카드 / Docs `reports/mckinsey`
- 스모크 (2026-07-31): 이전 상세 연타 이후 `browser-profile-mckinsey-search`로 hub조차 Access Denied → job `error`, **downloaded=0**. 복구 연타 없음. 본문 성공 수집은 차단 해제 후.
