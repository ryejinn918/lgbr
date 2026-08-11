"""Collect / document corpus MCP — search → detail (+ optional news, no PDF)."""

from __future__ import annotations

from typing import Any

from lgbr_api.news_articles import list_articles
from lgbr_api.reports import get_report as fetch_report, list_reports
from mcp.server import MCPServer
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings

from lgbr_mcp.branding import server_icons
from lgbr_mcp.config import allowed_hosts, public_base_url
from lgbr_mcp.formatting import dumps, report_detail_payload, serp_list_payload

COLLECT_SOURCES = (
    "fnguide, pwc, accenture, kpmg, ey, deloitte, "
    "hbr, hbrkorea, bain, mckinsey, bcg"
)

COLLECT_INSTRUCTIONS = f"""\
LGBR 산업 동향 문서 코퍼스(조회 전용).

규정:
- 원문 웹 URL(url)은 출처·인용용으로 제공합니다.
- 원문 PDF(바이트·다운로드 링크·파일 경로)는 제공하지 않습니다.
- 근거는 quality_json 품질검사·요약 필드와 원문 url을 사용하세요.

동향·섹터 질문이면 먼저 lgbr-consensus의 get_consensus(theme)를 보세요.
개별 보고서·근거가 필요할 때만 이 커넥터를 씁니다.

플로우:
1) search_reports(theme|q, source?, provider?, quality=pass 기본)
2) get_report(id) — 품질검사·요약 상세 + 원문 url (PDF 없음)
3) 속보/기사는 search_news(보조)

처리 종류:
- fnguide = sell_side (품질검사: 적합/부적합 게이트)
- 그 외 매체 = summary (한국어 요약·themes)

검색 조건 가이드:
- theme: ai, datacenter, macroeconomy, physical_ai, appliance, display, automotive, petrochemical
- q: 제목·키워드·요약
- source: {COLLECT_SOURCES}
- provider: 선호 하우스/증권사(attrs.provider)
"""


def build_collect_server(
    *,
    auth: AuthSettings | None = None,
    token_verifier: TokenVerifier | None = None,
) -> MCPServer:
    kwargs: dict[str, Any] = {}
    if auth is not None:
        kwargs["auth"] = auth
        kwargs["token_verifier"] = token_verifier
    mcp = MCPServer(
        name="lgbr-collect",
        title="LGBR 문서 코퍼스",
        instructions=COLLECT_INSTRUCTIONS,
        website_url=public_base_url(),
        icons=server_icons(),
        **kwargs,
    )

    @mcp.tool()
    def search_reports(
        theme: str | None = None,
        q: str | None = None,
        source: str | None = None,
        provider: str | None = None,
        quality: str | None = "pass",
        sort: str | None = "published_at",
        limit: int = 10,
        offset: int = 0,
    ) -> str:
        """보고서 검색(SERP). 기본 quality=pass. 상세는 get_report. PDF 없음.

        Args:
            theme: ai, datacenter, macroeconomy, physical_ai, appliance, display, automotive, petrochemical
            q: 제목·키워드·요약 검색
            source: fnguide, pwc, accenture, kpmg, ey, deloitte, hbr, hbrkorea, bain, mckinsey, bcg
            provider: 선호 하우스/증권사(부분일치)
            quality: pass(기본), fail, pending, unauditable, all
            sort: published_at(기본), page_count, last_seen_at
            limit: 기본 10, 최대 200
            offset: 페이지 오프셋
        """
        result = list_reports(
            source=source,
            theme=theme,
            quality=quality,
            q=q,
            provider=provider,
            sort=sort,
            limit=limit,
            offset=offset,
        )
        return dumps(serp_list_payload(result))

    @mcp.tool()
    def get_report(report_id: str) -> str:
        """보고서 메타·품질검사/요약 상세와 원문 웹 url. PDF는 제공하지 않음.

        Args:
            report_id: search_reports 결과의 id
        """
        result = fetch_report(report_id)
        return dumps(report_detail_payload(result))

    @mcp.tool()
    def search_news(
        q: str | None = None,
        source: str | None = "all",
        has_body: str | None = "all",
        include_body: bool = False,
        limit: int = 10,
        offset: int = 0,
    ) -> str:
        """뉴스 검색(보조). 기본은 메타만; 본문은 include_body=True.

        Args:
            q: 제목·URL·publisher 검색
            source: all 또는 arg
            has_body: all, yes, no
            include_body: True면 body_text 포함(길 수 있음)
            limit: 기본 10
            offset: 오프셋
        """
        result = list_articles(
            source=source,
            q=q,
            has_body=has_body,
            limit=limit,
            offset=offset,
        )
        items: list[dict[str, Any]] = []
        for row in result.get("items") or []:
            if not isinstance(row, dict):
                continue
            item = {
                "id": row.get("id"),
                "source": row.get("source"),
                "title": row.get("title"),
                "url": row.get("url"),
                "publisher": row.get("publisher"),
                "section": row.get("section"),
                "published_at": row.get("published_at"),
                "has_body": row.get("has_body"),
                "last_seen_at": row.get("last_seen_at"),
            }
            if include_body:
                item["body_text"] = row.get("body_text")
                item["body_fetch_error"] = row.get("body_fetch_error")
            items.append(item)
        return dumps(
            {
                "ok": result.get("ok", True),
                "message": result.get("message"),
                "total": result.get("total"),
                "body_counts": result.get("body_counts"),
                "items": items,
                "hint": "기사 페이지는 url. 본문이 필요하면 include_body=True.",
            }
        )

    return mcp


def transport_security_settings() -> TransportSecuritySettings:
    hosts = allowed_hosts()
    if not hosts:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    origins = []
    for h in hosts:
        host_only = h.split(":")[0]
        origins.append(f"https://{host_only}:*")
        origins.append(f"http://{host_only}:*")
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )
