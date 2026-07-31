# lgbr-mcp

Claude용 조회 전용 MCP (본 API `lgbr-api`와 별도 프로세스). 인증은 **OAuth 로그인 한 가지**만 지원합니다.

## Public URL

```
https://lgbrmcp.magpielabs.co.kr
```

| Path | 용도 |
|------|------|
| `POST /mcp/collect` | 문서 코퍼스 (`search_reports` / `run_sql` → `get_report`, 뉴스 보조) |
| `POST /mcp/consensus` | 섹터 동향 초안 (`get_consensus`) |
| `GET/POST /login` | OAuth 로그인 |
| `GET /health` | 헬스 (공개) |

## 규정 (collect)

| 항목 | 제공 |
|------|------|
| 원문 웹 URL (`url`) | 예 — 출처·인용 |
| 원문 PDF (바이트·다운로드 링크·파일 경로) | **아니오** |
| 품질/요약 (`quality_json`, SERP summary 등) | 예 |

## Env

| 변수 | 설명 |
|------|------|
| `LGBR_MCP_PUBLIC_BASE_URL` | `https://lgbrmcp.magpielabs.co.kr` |
| `LGBR_MCP_ALLOWED_HOSTS` | `lgbrmcp.magpielabs.co.kr` |
| `LGBR_MCP_ENV` | `production` |
| `LGBR_MCP_OAUTH_USERNAME` | Connect 로그인 계정 |
| `LGBR_MCP_OAUTH_PASSWORD` | Connect 로그인 비밀번호 |
| `LGBR_MCP_SIGNING_SECRET` | (레거시 서명 유틸; collect는 PDF URL을 발급하지 않음) |
| `DATABASE_URL` | Postgres (api와 동일). SQL 탐색은 `SET ROLE lgbr_mcp_ro` |

마이그레이션 `031_mcp_reports_sql.sql`이 뷰 `mcp_reports`·롤 `lgbr_mcp_ro`·`pg_trgm` 인덱스를 만듭니다.

## Claude / ChatGPT

Settings → Connectors → Add custom connector (×2):

1. `https://lgbrmcp.magpielabs.co.kr/mcp/collect`
2. `https://lgbrmcp.magpielabs.co.kr/mcp/consensus`

OAuth Client ID / Secret는 **비움**(DCR). Connect 후 `LGBR_MCP_OAUTH_USERNAME` / `LGBR_MCP_OAUTH_PASSWORD`로 로그인.

### Collect 도구

1. **`describe_schema`** — `mcp_reports` 컬럼·예시 SELECT  
2. **`run_sql(sql)`** — 표준 SQL, Postgres 롤 `lgbr_mcp_ro`로 실행 (`mcp_reports`만 SELECT)  
3. **`search_reports` → `get_report`** — 간단 검색·상세 (요약·원문 url, PDF 없음)  
4. **`search_news`** — 보조

`source`: fnguide, pwc, accenture, kpmg, ey, deloitte, hbr, hbrkorea, bain, mckinsey, bcg  
`audit_kind`: fnguide=`sell_side`, 그 외=`summary`

### Consensus

`get_consensus(theme)` — 분석 축 + 골격 + 보고서 초안 (최신 ended)

## Local

```bash
uv sync
python db/apply_migrations.py
python -m lgbr_mcp --host 127.0.0.1 --port 8788
# pm2: ecosystem.config.cjs → lgbr-mcp
```
