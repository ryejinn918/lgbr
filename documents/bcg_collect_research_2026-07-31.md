# BCG 수집 조사 (2026-07-31, 갱신 2026-08-01)

무계정. 아티팩트: `.crawler/snapshots/bcg-research/` (`findings.json`, 스크린샷).

JSON 목록 API 없음. allowlist HTML GET + 상세 PDF만. 임의 `/publications/{year}/{slug}`·PDF slug 추측 금지.

## Hub

- URL: `https://www.bcg.com/`
- Access Denied / 로그인월: **없음**
- 쿠키: `#onetrust-accept-btn-handler` / Accept (보이면; 애드혹/probe)
- 네비: **Our Insights** → **Featured Insights** Visit Page → `https://www.bcg.com/publications`

## 목록 표면 (확인)

### Featured Insights

- URL: `https://www.bcg.com/publications`
- 카드: `a[href*="/publications/"]` 중 `/publications/{YYYY}/{slug}`
- 날짜: 카드 근처 `JULY 31, 2026` 형태
- 첫 화면 카드 수: **6** (정적 HTML 동일)
- Load More: **미확인** (라벨 없음). 스크롤로 카드 증가 없음.

### Industry / Capability (테마 프로필용)

데스크 테마 → **probe로 카드 ≥1 확인된** 목록 URL만 (`bcg_browser.PROFILES`):

| profile | list_urls (확인) |
|---------|------------------|
| report | `/publications` |
| ai | `/capabilities/artificial-intelligence`, `…/generative-ai` |
| datacenter | `/capabilities/…/cloud-computing`, `/industries/energy/power-utilities`, `…/semiconductors` |
| physical_ai | `/capabilities/manufacturing/industry-4.0`, `…/machinery-industrial-automation` |
| appliance | `/industries/consumer-products-industry/overview` |
| display | `…/future-of-television`, `…/technology-industry` |
| automotive | `/industries/automotive/overview` |
| petrochemical | `/industries/industrial-goods/chemicals` |

Industry/capability 페이지는 featured 카드 소수(정적). 페이지네이션 없음.

## 상세 / PDF

- PDF: `https://web-assets.bcg.com/pdf-src/prod-live/{slug}.pdf` (상세 HTML의 `.pdf` 링크만; slug 추측 금지)
- 없으면 검증된 `page.pdf` (LazyCaptureBrowser)
- Access Denied·빈 본문·비 `%PDF`는 `downloaded`로 치지 않음

## Transport

| 경로 | 방식 |
|------|------|
| **search** (`bcg_report`) | **HTTP** (`bcg_http`: list HTML → detail → PDF). PDF 없을 때만 page.pdf |
| **adhoc** / **probe** | Patchright 브라우저 (`bcg_browser`, CDP) |

스모크: `uv run python crawler/scripts/bcg_http_smoke.py --profile report --limit 1`

## Probe

```bash
uv run python crawler/scripts/bcg_adhoc_probe.py --verify-profiles
```

## 자동화 절차 (search / HTTP)

1. 프로필 allowlist `list_urls`만 GET (상한 = `max_pages`)
2. 카드 파싱: `/publications/{year}/{slug}` + 날짜·제목
3. 미보유 1건씩 상세 GET → PDF GET (또는 page.pdf 폴백)
4. item delay 기본 **2s**

## 현재 상태

- 잡: `bcg_report` HTTP + `profile` (desk theme)
- FE: `BcgRunPage` 프로필 선택 · 기본 간격 2초 · 애드혹 CDP
- 요약: `audit_report_quality.py --source bcg` (수집 안정 후)
