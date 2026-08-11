# lgbr-mcp

Claude용 조회 전용 MCP (본 API `lgbr-api`와 별도 프로세스). 인증은 **OAuth 로그인 한 가지**만 지원합니다.

## Public URL

```
https://lgbrmcp.magpielabs.co.kr
```

| Path | 용도 |
|------|------|
| `POST /mcp/collect` | 문서 코퍼스 (`search_reports` → `get_report`, 뉴스 보조) |
| `POST /mcp/consensus` | 섹터 동향 초안 (`get_consensus`) |
| `GET/POST /login` | OAuth 로그인 |
| `GET /health` | 헬스 (공개) |

## 규정 (collect)

| 항목 | 제공 |
|------|------|
| 원문 웹 URL (`url`) | 예 — 출처·인용 |
| 원문 PDF (바이트·다운로드 링크·파일 경로) | **아니오** |
| 품질검사·요약 (`quality_json`, SERP summary 등) | 예 |

## Env

| 변수 | 설명 |
|------|------|
| `LGBR_MCP_PUBLIC_BASE_URL` | `https://lgbrmcp.magpielabs.co.kr` |
| `LGBR_MCP_ALLOWED_HOSTS` | `lgbrmcp.magpielabs.co.kr` |
| `LGBR_MCP_ENV` | `production` |
| `LGBR_MCP_OAUTH_USERNAME` | Connect 로그인 계정 |
| `LGBR_MCP_OAUTH_PASSWORD` | Connect 로그인 비밀번호 |
| `LGBR_MCP_SIGNING_SECRET` | (레거시 서명 유틸; collect는 PDF URL을 발급하지 않음) |
| `DATABASE_URL` | Postgres (api와 동일) |

## Claude / ChatGPT

Settings → Connectors → Add custom connector (×2):

1. `https://lgbrmcp.magpielabs.co.kr/mcp/collect`
2. `https://lgbrmcp.magpielabs.co.kr/mcp/consensus`

OAuth Client ID / Secret는 **비움**(DCR). Connect 후 `LGBR_MCP_OAUTH_USERNAME` / `LGBR_MCP_OAUTH_PASSWORD`로 로그인.

커넥터를 채팅에서 켠 뒤, Project 지침에 필요하면 아래만 넣으면 됩니다.

```text
LG MRI paid literature (LGBR). Prefer for paywalled items + Korean summaries.
Sector theme ask (Physical AI, datacenter, …): get_consensus(theme=…) once as background,
then search_reports → get_report for citations/lists (증권사: source=fnguide).
HBR briefing only: search_reports(source="hbr", sort="published_at") → get_report on pass.
Open consulting (kpmg/ey/…): web may be fresher if corpus misses a public URL.
Unaudited latest titles only: quality=pending.
```

### Collect 도구

1. **`search_reports` → `get_report`** — 수집 코퍼스 검색·요약(url, PDF 없음)  
2. **`search_news`** — 속보 보조

`source`: fnguide, pwc, accenture, kpmg, ey, deloitte, hbr, hbrkorea, bain, mckinsey, bcg

### Consensus

`get_consensus(theme)` — 섹터 초안(axes / frame)

## Local

```bash
uv sync
python db/apply_migrations.py
python -m lgbr_mcp --host 127.0.0.1 --port 8788
# pm2: ecosystem.config.cjs → lgbr-mcp
```
