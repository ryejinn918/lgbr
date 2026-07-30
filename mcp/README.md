# lgbr-mcp

Claude용 조회 전용 MCP (본 API `lgbr-api`와 별도 프로세스). 인증은 **OAuth 로그인 한 가지**만 지원합니다.

## Public URL

```
https://lgbrmcp.magpielabs.co.kr
```

| Path | 용도 |
|------|------|
| `POST /mcp/collect` | 보고서·뉴스 코퍼스 |
| `POST /mcp/consensus` | 섹터 컨센서스 |
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

## Claude 웹

Settings → Connectors → Add custom connector (×2):

1. `https://lgbrmcp.magpielabs.co.kr/mcp/collect`
2. `https://lgbrmcp.magpielabs.co.kr/mcp/consensus`

OAuth Client ID / Secret는 **비움**. Connect 후 `LGBR_MCP_OAUTH_USERNAME` / `LGBR_MCP_OAUTH_PASSWORD`로 로그인.

## Local

```bash
uv sync
python -m lgbr_mcp --host 127.0.0.1 --port 8788
# pm2: ecosystem.config.cjs → lgbr-mcp
```
