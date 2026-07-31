# HBR Korea 리스트·본문 수집 애드혹 검증 (2026-07-31)

로그인 CDP 세션으로 검증. 아티팩트: `.crawler/snapshots/hbrkorea-research/` (`findings.json`, 스크린샷, `page-capture-*.pdf`).

## 목록

- URL: `https://www.hbrkorea.com/article/latest` (+ `/page/{N}`)
- DOM: `ul.post_list > li` / `a[href*="/article/view/"]` / `.post_ho`
- 페이지네이션: `div.paging a` 클릭으로 이동 (직접 `goto`는 간헐 `ERR_HTTP_RESPONSE_CODE_FAILURE` — 클릭 또는 Referer 권장)
- 최근 3개월(cutoff `2026-05-01`): **약 4페이지**, 샘플 114건 중 within **101건** (page 4에서 outside 시작)
- 매거진 날짜 `2026. 7-8월호` → 호 시작월 1일로 파싱

## 본문

- 로그인 상세: `#article_body` **8364자**, `section.preview` **없음** → 전문 확보 가능
- 페이월 지표는 **`section.preview` 존재**뿐. 본문 길이 임계값(예: 1500)은 검증된 값이 아니며, 짧은 편집장 서문(700–1400자)을 오탐함 → 빈 페이지용 하한(~200)만 사용
- `/article/pdf_download/article_no/{n}`: 로그인 후에도 **`text/html`** (실제 PDF 아님)
- Playwright `page.pdf()`: **성공** (~563KB) → **본문 확보 전략 = page.pdf 캡처**

## 자동화 (구현됨)

1. `sources/hbrkorea_browser.py` + `jobs/hbrkorea_report.py` — list-while-download, `period_months=3`
2. 목록: `/article/latest` paging(클릭 우선), `.post_ho` cutoff로 stop
3. 파일: 로그인 브라우저에서 상세 `page.pdf` → `reports` (`source=hbrkorea`)
4. FE: `/collect/hbrkorea/list/search` 검색 실행 (계정 env: `HBRKOREA_USER_ID` / `HBRKOREA_PASSWORD`)
5. `pdf_download` URL은 사용하지 않음

## 리스크

- 단일 세션 계정
- 매거진 호수 날짜는 일 단위가 아님 (월 단위 근사)
- 직접 URL goto보다 페이지 클릭이 안정적
