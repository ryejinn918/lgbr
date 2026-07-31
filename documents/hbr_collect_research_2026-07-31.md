# HBR.org 수집 조사 (2026-07-31)

영문 HBR (`https://hbr.org/`). 한글판 `hbrkorea`와 별도.  
아티팩트: `.crawler/snapshots/hbr-research/` (`findings.json`, 스크린샷).

## 로그인 (차단됨 — 추가 시도 금지)

- `/signin` URL: **404** (Page Not Found)
- 확인된 로그인 UI: hub `#sign-in-button-header` → `[role=dialog]` 모달
  - `input[name="emailAddress"]`, `input[name="password"]`
  - `button[type=submit]` 텍스트 `Sign In` (입력 전에는 disabled)
  - invisible reCAPTCHA
- `crawler/.env`의 `HBR_USER_ID` / `HBR_PASSWORD`로 제출 →  
  **「invalid email and password combination」** (잔여 시도 안내 후 **재시도 중단**)
- 자격증명은 정기간행물 엑셀 Digital+Print 행과 동기화했으나 사이트에서 거절됨  
  → **비밀번호/계정 상태 확인 필요. 자동 로그인 연타 금지.**

## Hub / 네비 (확인)

- Hub: `https://hbr.org/`
- Latest: `https://hbr.org/the-latest`
- Magazine: `https://hbr.org/magazine`
- 아티클 URL 형태: `https://hbr.org/{YYYY}/{MM}/{slug}`

## 목록 (공개 세션)

- Latest 목록에서 아티클 링크·`Load More Items`(`a`, href `#`) 클릭으로 항목 수 증가 확인
- 카드 제목/날짜 선택자는 렌더에 따라 비어 보일 수 있음 → 로그인 성공 후 DOM 재확인 필요
- Magazine 이슈 링크는 이번 공개 조사에서 안정적으로 못 잡음 → 후속

## 상세 (공개 1건)

- 예: `…/2026/07/the-hidden-realities-of-ai-adoption`
- `article` 존재, **paywall 요소 존재**, 공개 `p` 약 1개(~400자) → 전문 아님
- PDF 링크 없음
- 공개 상태에서 `page.pdf`는 성공으로 치지 않음 (페이월/짧은 본문)

## 자동화에 쓸 절차 (로그인 성공 전제)

1. `HBR_*` env → hub Sign In 모달 로그인 (영속 프로필 `browser-profile-hbr`)
2. `https://hbr.org/the-latest` → 카드 수집 → UI에 `Load More Items` 있을 때만 클릭
3. **한 건씩** 상세 + delay
4. 로그인 후에도 paywall/짧은 본문이면 `no_download`; 충분하면 `page.pdf` (Access Denied·페이월은 downloaded 금지)
5. HTTP 목록/상세 연타 없음

## 대기

- `wait_until=domcontentloaded`, 페이지 ~2–3.5s, 아이템 간 ≥4–5s

## Phase 상태

- Phase 1: 레지스트리·`hbr_login`/`hbr_session`·Dashboard/애드혹 구현
- Phase 2: 본 메모 + `.crawler/snapshots/hbr-research/`
- Phase 3: `hbr_browser.py` + `hbr_report.py` + allowlist/FE/`reports/hbr` 배선 완료
- Phase 4 스모크: **미실행** — 로그인 거절로 잔여 시도 보호.  
  `crawler/.env`의 `HBR_PASSWORD`를 hbr.org에서 수동 확인한 뒤  
  `limit=2~3` 검색 + `pdftotext` + `audit_report_quality.py --source hbr` 진행
