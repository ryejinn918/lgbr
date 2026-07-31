# lgbr-mcp

Claude용 조회 전용 MCP (본 API `lgbr-api`와 별도 프로세스). 인증은 **OAuth 로그인 한 가지**만 지원합니다.

## Public URL

```
https://lgbrmcp.magpielabs.co.kr
```

| Path | 용도 |
|------|------|
| `POST /mcp/collect` | 문서 코퍼스 (`search_reports`→`get_report`, 뉴스 보조) |
| `POST /mcp/consensus` | 섹터 동향 초안 (`get_consensus`) |
| `GET/POST /login` | OAuth 로그인 |
| `GET /files/reports/{id}?exp=&sig=` | 서명 PDF (HMAC, TTL 기본 15분) |
| `GET /health` | 헬스 (공개) |

## Env

| 변수 | 설명 |
|------|------|
| `LGBR_MCP_PUBLIC_BASE_URL` | `https://lgbrmcp.magpielabs.co.kr` |
| `LGBR_MCP_ALLOWED_HOSTS` | `lgbrmcp.magpielabs.co.kr` |
| `LGBR_MCP_ENV` | `production` |
| `LGBR_MCP_OAUTH_USERNAME` | Connect 로그인 계정 |
| `LGBR_MCP_OAUTH_PASSWORD` | Connect 로그인 비밀번호 |
| `LGBR_MCP_SIGNING_SECRET` | PDF URL HMAC 시크릿 |
| `LGBR_MCP_PDF_TTL_SECONDS` | 서명 URL TTL (기본 `900`) |
| `DATABASE_URL` | Postgres (api와 동일) |

## Claude / ChatGPT

Settings → Connectors(또는 Plugins) → Add custom connector (×2):

1. `https://lgbrmcp.magpielabs.co.kr/mcp/collect`
2. `https://lgbrmcp.magpielabs.co.kr/mcp/consensus`

OAuth Client ID / Secret는 **비움**(DCR). Connect 후 `LGBR_MCP_OAUTH_USERNAME` / `LGBR_MCP_OAUTH_PASSWORD`로 로그인. ChatGPT도 동일(OAuth + DCR + scope `mcp`).

### 동향 조사 플로우

1. 섹터 동향 → **consensus** `get_consensus(theme)` 먼저  
2. 개별 보고서 → **collect** `search_reports(theme|q, source?, provider?)` → `get_report`  
3. 속보 → `search_news` (보조)

`provider` = 선호 하우스/증권사(종목·섹터마다 다를 수 있음). `source` = 채널(fnguide·deloitte 등).

### Consensus

`get_consensus(theme)` — 분석 축 + 골격 + 보고서 초안 (최신 ended)

### Collect 도구 위계

1. **기본:** `search_reports` → `get_report`  
2. **보조:** `search_news`

## Local

```bash
uv sync
python -m lgbr_mcp --host 127.0.0.1 --port 8788
# pm2: ecosystem.config.cjs → lgbr-mcp
```
