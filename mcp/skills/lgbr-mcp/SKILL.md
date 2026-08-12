---
name: lgbr-mcp
description: >-
  LGBR paid MCP connectors complement (do not replace) web search:
  lgbr-consensus (get_consensus) and lgbr-collect (search_reports → get_report
  summaries, search_news). Use alongside web for sector trends, 동향, 섹터,
  컨센서스, HBR/FnGuide/paywalled briefs, and in-house Korean summaries. Prefer
  LGBR for curated paid corpus; still use web for freshness, open pages, and
  gaps. First substantive reply: deliver near-full consensus frame (Evidence +
  footnotes); do not paraphrase-down. Synthesis/compression only on follow-up
  request. Keep reading until research is sufficient.
---

# LGBR MCP (consensus + literature)

LGBR connectors are an **extra paid layer**, not the whole research stack.
Call them early when relevant — and **still use web search** for freshness,
public pages, and anything the corpus misses.

| Connector | Tools | Role |
|-----------|--------|------|
| **lgbr-consensus** | `get_consensus(theme)` | In-house sector draft (`axes` + `frame`) |
| **lgbr-collect** | `search_reports` → `get_report`, `search_news` | Paid corpus **summaries** + `url` (no PDF) |

## Themes (`theme`)

`ai` AI · `datacenter` 데이터센터 · `macroeconomy` 거시경제 · `physical_ai` 피지컬 AI · `appliance` 가전 · `display` 디스플레이 · `automotive` 자동차 · `petrochemical` 석유화학

## Sources (`source` on collect)

`fnguide`, `pwc`, `accenture`, `kpmg`, `ey`, `deloitte`, `hbr`, `hbrkorea`, `bain`, `mckinsey`, `bcg`

## LGBR vs web

| Prefer **LGBR** | Prefer **web** (then optionally re-check LGBR) |
|-----------------|-----------------------------------------------|
| Paywalled / subscription (HBR, FnGuide, …) + Korean `quality_json` | Recent open consulting (kpmg, ey, …) — corpus discovery lags the public site |
| Covered-theme sector draft (`get_consensus`) | Breaking news, filings, blogs, vendor posts not in corpus |
| Normalized title / date / source for cite | Exact public URL or page the user named that `search_reports` misses |
| In-house audit/summary already done | Freshness check when `run.ended_at` / report `published_at` looks stale |

**Default for mixed asks:** run LGBR **and** web. Do not refuse web because LGBR returned something. Corpus hit ≠ complete picture.

## Routing

1. **Covered-theme 동향 / 섹터 합의** → `get_consensus(theme)` **once** + collect for depth; **also web** for recent public signals the frame may omit.
2. **문헌·브리핑·인용** → `search_reports` → `get_report` on promising `quality=pass` hits. SERP `summary` is a clip; open `get_report` for full `quality_json`. Parallel web when you need open/latest pages.
3. **HBR-only** → `search_reports(source="hbr", sort="published_at")` → `get_report` on pass. Skip consensus unless they also want sector synthesis.
4. **속보** → web and/or `search_news` (secondary). Prefer reports for HBR/consulting.
5. **Open consulting / public URL missing in corpus** → **web first**, then re-check collect for a Korean summary after ingest.
6. **Titles only / unaudited** → `quality=pending` or `all` (may lack summary).

Skip consensus if already fetched this turn for that theme, or theme is outside the table.

## Research habit (do not under-read; do not DB-only)

1. **Map** the ask → theme / keywords / sources; decide what needs paid corpus vs public web.
2. **Background** (if sector trend): `get_consensus` once; note claims and gaps (`미충족 보강` = gap, not fact).
3. **Corpus pass**: `search_reports` (`quality=pass`). Set `source` when targeting a medium (`q` alone often returns 0). Page with `offset` if needed. Open several `get_report`s — not one title.
4. **Web pass** (same turn when the ask is timely, comparative, or public-facing): search/open relevant public pages. If a page should live in LGBR but is missing, say so and use the web result.
5. **Loop until sufficient**:
   - Key claims backed by corpus summary **and/or** a concrete web source (label which).
   - Competing views covered when comparative.
   - Numbers/dates not invented; stale corpus angles cross-checked on the web when freshness matters.
   - Thin corpus → refine collect **and** widen web — not collect-only retries forever.
6. **Stop** when another pass only repeats the same material (corpus or web) and gaps are stated honestly.
7. **First reply = delivery**, not a rewritten thesis essay. Do not paraphrase-down the frame before the user has seen near-full density.

Anti-patterns:
- Ignoring LGBR when the ask is paywalled / covered-theme 동향
- **DB-only**: skipping web after any corpus hit
- Stopping after one `search_reports`
- Citing titles without `get_report`
- Asking for PDF bytes
- Rewriting `pillar_sketch` into a new TOC (use frame Deep Dive structure as-is on first reply)
- **Paraphrase-down** / first-reply summary-only / Exec Summary alone
- Dropping footnotes, numbers, or Evidence bullets from the frame
- Bare claims with no house/title/date (or URL)

## 첫 응답 (delivery) — 원문 밀도 우선

첫 substantive 답은 `get_consensus`의 `frame`(filled 우선)을 **거의 원문 분량·구조로 전달**한다. Claim / Evidence(메커니즘·수치) / 쪽 각주 / `참고 보고서`를 요약·병합·삭제하지 말 것.

**포함할 것**
- Executive Summary
- 주제별 Deep Dive (frame에 있는 절 구조 그대로; Claim, Evidence, 현황·전망, 플레이어, 성장·저해, Watch)
- `미충족 보강`은 gap으로 표시 (사실처럼 쓰지 않음)
- `참고 보고서` 목록

**앞에만 짧게 허용 (1~3문장)**
- 축들 사이에서 읽은 긴장/주장 한 줄 (선택)
- `run.ended_at` / `published_at` 기준 웹 신선도 메모 한 줄 (해당 시)

그 다음 본문은 frame 밀도를 희생하지 않는다.

**금지**
- “핵심만 정리하면”, Exec만 옮기기, 몇 개 bullet로 뭉개기
- 수치·각주(`[KB, 1쪽]`, `[하우스, 짧은제목, YYYY-MM-DD]` 등) 제거
- `pillar_sketch`를 새 목차로 갈아끼우기 (첫 응답에서는 frame Deep Dive를 그대로)

**collect만 쓸 때**
- SERP `summary` clip을 한 번 더 줄이지 말 것. `get_report`의 `quality_json` 요지 + `report.url`을 충분히 남긴다.

**출처**
- frame 각주 형식을 유지; collect는 요지 + url; 웹은 URL. 사내 요약 vs 라이브 웹을 구분. PDF path/download 금지.

## 후속 응답 (synthesis) — 압축·논지는 요청 후에만

사용자가 “짧게”, “한 장으로”, “논지만”, “그래서 뭐야”처럼 **압축·재구성을 요청할 때만** 아래를 적용한다. 그때도 핵심 수치·각주는 유지.

`axes.pillar_sketch`와 주제 목록은 **커버리지 지도**이지 새 리포트 목차가 아니다. 축을 “축1→축2→축3” 나열로 다시 쓰면 주장 없는 글이 된다.

1. 축들 *사이의* 긴장·모순·인과를 하나 고른다.
2. 그것으로 **단일 주장 한 문장**을 뼈대로 쓰고, 절은 그 주장의 근거로만 둔다. 안 쓰는 축이 있어도 된다.
3. 신선도: 컨센서스가 못 잡은 규제·사건이 웹에 있으면 논지 출발점으로 쓸 수 있다.
4. 숫자가 주장을 직접 지지하는지 자문한다. 아니면 빼거나 “확인 필요”.

**체크:** “그래서 뭐?(so what)”에 한 문장으로 답할 수 없으면 아직 나열이다.
