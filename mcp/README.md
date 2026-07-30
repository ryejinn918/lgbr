# lgbr-mcp

Claude Enterprise용 조회 전용 MCP (본 API `lgbr-api`와 별도 프로세스).

## Public URL (Cloudflare Tunnel)

```
https://lgbrmcp.magpielabs.co.kr
```

| Path | 용도 | 인증 |
|------|------|------|
| `POST /mcp/collect` | 보고서·뉴스 코퍼스 커넥터 | Bearer / X-API-Key **필수** |
| `POST /mcp/consensus` | 섹터 컨센서스 커넥터 | 동일 |
| `GET /files/reports/{id}?exp=&sig=` | 서명 PDF (헤더 없음) | HMAC TTL (기본 15분) |
| `GET /health` | 헬스 | 공개 |

로컬: `127.0.0.1:8788` ← tunnel ingress `lgbrmcp.magpielabs.co.kr`.

## Env

| 변수 | 설명 |
|------|------|
| `LGBR_MCP_PUBLIC_BASE_URL` | `https://lgbrmcp.magpielabs.co.kr` |
| `LGBR_MCP_ALLOWED_HOSTS` | `lgbrmcp.magpielabs.co.kr` |
| `LGBR_MCP_ENV` | `production` (https URL이면 production으로 간주) |
| `LGBR_MCP_API_KEY` | 커넥터용 API 키 (**필수**, insecure 로컬 제외) |
| `LGBR_MCP_SIGNING_SECRET` | PDF 서명 시크릿 (**필수**, API 키와 별개) |
| `LGBR_MCP_PDF_TTL_SECONDS` | 서명 URL TTL (기본 `900`) |
| `LGBR_MCP_ALLOW_INSECURE` | `1`이면 로컬에서 키 없이 기동 (https/production에서는 불가) |
| `DATABASE_URL` | Postgres (api와 동일) |

`LGBR_API_KEY`(UI/API)와 MCP 키·서명 시크릿을 공유하지 마세요.

## Cloudflare Tunnel

`~/.cloudflared/config.yml` ingress에:

```yaml
  - hostname: lgbrmcp.magpielabs.co.kr
    service: http://127.0.0.1:8788
```

DNS: Cloudflare에서 `lgbrmcp` CNAME → 해당 터널 (nest1/chamber1과 동일).  
**Cloudflare Access는 사용하지 않음** (Claude 서버·서명 PDF GET과 충돌).

## Claude Enterprise

Admin → Connectors → Add custom connector (×2):

1. Collect: `https://lgbrmcp.magpielabs.co.kr/mcp/collect`
2. Consensus: `https://lgbrmcp.magpielabs.co.kr/mcp/consensus`

각각 **Request headers** → `authorization` 값: `Bearer <LGBR_MCP_API_KEY>`  
(`Bearer`와 공백 포함. Claude는 스킴을 자동 추가하지 않음.)

## Local

```bash
# 키 필수 (또는 LGBR_MCP_ALLOW_INSECURE=1)
uv sync
python -m lgbr_mcp --host 127.0.0.1 --port 8788
# pm2: ecosystem.config.cjs → lgbr-mcp
```
