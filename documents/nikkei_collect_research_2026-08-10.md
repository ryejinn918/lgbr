# Nikkei (www.nikkei.com) 수집 리서치 (2026-08-10)

아티팩트: `.crawler/snapshots/nikkei-research/`

## 로그인·기사

- 허브: `https://www.nikkei.com/`
- 로그인: 日経ID (`/login` → `id.nikkei.com`), Excel BP 계정(`raha@lgbr.co.kr`)으로 애드혹 성공
- 기사 URL: `/article/DGXZQO…/` → `source_key`
- 유료 배지(`[有料会員限定記事]`)여도 **로그인 세션에서는 본문 전문** 확인

## RSS (섹션 목록)

공식 `www.nikkei.com/rss`는 404. 일본어 본편 RSS는 중단된 상태로 알려짐.

**1차 목록 소스 (채택):** 제3자 미러 `assets.wor.jp`

| section id | label | RSS | category |
|---|---|---|---|
| news | 速報 | `…/nikkei/news.rdf` | `/news/category/` |
| business | ビジネス | `…/nikkei/business.rdf` | `/news/category/business/` |
| economy | 政治・経済 | `…/nikkei/economy.rdf` | `/news/category/economy/` |
| markets | マーケット | `…/nikkei/markets.rdf` | `/news/category/markets/` |
| technology | テクノロジー | `…/nikkei/technology.rdf` | `/news/category/technology/` |
| international | 国際・アジア | `…/nikkei/international.rdf` | `/news/category/international/` |
| sports | スポーツ | `…/nikkei/sports.rdf` | `/news/category/sports/` |
| society | 社会 | `…/nikkei/society.rdf` | `/news/category/society/` |

검증: `economy.rdf` 상위 기사가 라이브 카테고리 페이지와 일치. 스냅샷당 ~30건, title/`dc:date`/link만 (본문 없음).

HTTP 403으로 확인되지 않은 slug 예: politics, tech, opinion, culture, lifestyle, financial, jinji.

**2차:** 같은 slug의 카테고리 HTML에서 `/article/DGXZQO` 링크 보강.

참고: [日経ビジネス 공식 RSS](https://business.nikkei.com/atcl/gen/19/00062/102700043/)는 별 매체(`business.nikkei.com`). Asia RSS는 영어판.

## 파이프라인

1. `capability=feed` + `section` → RSS(+HTML) → `news_articles` (`attrs.section`)
2. `capability=fetch_body` → 로그인 Patchright (`browser-profile-nikkei-body`) → `body_text`

FE: Collect → Nikkei → 피드(섹션) / 본문.
