# Nikkei xTECH (日経クロステック) 수집 리서치 (2026-07-31)

아티팩트: `.crawler/snapshots/nikkeixtech-research/`

## 허브·로그인

- 허브: `https://xtech.nikkei.com/`
- 로그인: BP SSO (`bpsso_xtech.js`) → `bpsso.nikkei.com` → **日経ID** (`id.nikkei.com`)
  - 2단계: email → `次に進む` → password → `次に進む`
  - 신규/이질 환경에서는 **`/login/challenge` OTP**(메일 ワンタイムパスワード)
- Excel BP 계정(`raha@lgbr.co.kr`) 비밀번호는 통과하나, 자동화 프로필에서는 OTP 필수
- 비로그인 기사 샘플: 본문 ~1300자, paywall 카피 있음 → **전문은 로그인 필요**
- 애드혹: source `nikkeixtech`, env `NIKKEIXTECH_*` (또는 `NIKKEI_*` fallback), CDP를 로그인 전에 열어 OTP 입력

## 목록

- 新着: `https://xtech.nikkei.com/top/latest.html` (타이틀: 新着記事一覧)
  - 기사 URL 패턴: `/atcl/nxt/column/{series}/{YYMMDDNNN}/` (시리즈 허브 URL도 혼재 → **상세 slug 있는 링크만** 수집)
  - UI: 「もっと見る」로 추가 로드 (`latest.js` → BP `executeBpsearch`, rows≈20)
  - 첫 화면 날짜 샘플: `2026.07.31` … `2026年6月17` (수주~수개월 경계는 offset 반복으로 확인)
  - **3개월 백필은 「もっと見る」/API offset 반복 + 날짜 cutoff 필요**
- RSS: `https://xtech.nikkei.com/rss/index.rdf` (~100건, ~1–1.5일) — 증분용, 3개월 단독 불가

## 다음

1. OTP 완료 세션으로 유료 기사 본문 길이·저장 포맷(`news_articles` vs `reports`/`page.pdf`) 확정
2. latest + bpsearch cutoff(3개월) list-while-download 잡
3. FE 검색 실행 페이지 (HBR형)
