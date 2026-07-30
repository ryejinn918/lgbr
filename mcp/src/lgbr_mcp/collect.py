"""Set A — collect / document corpus MCP tools (SERP + links)."""

from __future__ import annotations

from typing import Any

from lgbr_api.news_articles import list_articles
from lgbr_api.reports import coverage_by_week, get_report, list_reports
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from lgbr_mcp.config import allowed_hosts
from lgbr_mcp.formatting import dumps, report_detail_payload, serp_list_payload

COLLECT_INSTRUCTIONS = """\
LGBR 산업 동향 문서 코퍼스(조회 전용).
리서처가 보고서를 찾을 때: search_reports로 후보를 고른 뒤 각 항목의 pdf_url 또는 source_url을 열어 원문을 읽으세요.
이 서버는 PDF 본문 텍스트를 추출·반환하지 않습니다. 웹에서 PDF 링크를 여는 것과 같습니다.
기본으로 quality=pass 필터를 권장합니다.
"""


def build_collect_server() -> MCPServer:
    mcp = MCPServer(
        name="lgbr-collect",
        title="LGBR 문서 코퍼스",
        instructions=COLLECT_INSTRUCTIONS,
    )

    @mcp.tool()
    def search_reports(
        source: str | None = None,
        theme: str | None = None,
        quality: str | None = "pass",
        status: str | None = None,
        q: str | None = None,
        sort: str | None = "published_at",
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        """보고서 검색(SERP). 원문은 결과의 pdf_url·source_url을 열어 읽습니다.

        Args:
            source: fnguide, pwc, accenture, kpmg, ey, deloitte, all 또는 생략
            theme: ai, datacenter, macroeconomy, physical_ai, appliance, display, automotive, petrochemical
            quality: pass(기본), fail, pending, unauditable, all(전체)
            status: listed, downloaded, blind, no_download, failed
            q: 제목 검색어
            sort: published_at, page_count, last_seen_at
            limit: 기본 20, 최대 200
            offset: 페이지 오프셋
        """
        result = list_reports(
            source=source,
            theme=theme,
            quality=quality,
            status=status,
            q=q,
            sort=sort,
            limit=limit,
            offset=offset,
        )
        return dumps(serp_list_payload(result))

    @mcp.tool()
    def get_report(report_id: str) -> str:
        """보고서 메타·품질 심사 상세와 원문 링크(pdf_url, source_url).

        Args:
            report_id: search_reports 결과의 id
        """
        result = get_report(report_id)
        return dumps(report_detail_payload(result))

    @mcp.tool()
    def search_news(
        source: str | None = "all",
        q: str | None = None,
        has_body: str | None = "all",
        include_body: bool = True,
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        """ARG 등 뉴스 기사 검색. url로 원문을 열고, include_body면 저장된 body_text도 포함.

        Args:
            source: all 또는 arg
            q: 제목·URL·publisher 검색
            has_body: all, yes, no
            include_body: True면 body_text 포함(길 수 있음)
            limit: 기본 20
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
                "hint": "기사 원문 페이지는 각 항목 url을 여세요.",
            }
        )

    @mcp.tool()
    def get_coverage(weeks: int = 13) -> str:
        """소스별 주간 발행 커버리지(빈 주 확인용).

        Args:
            weeks: 최근 주 수(기본 13, 최대 52)
        """
        return dumps(coverage_by_week(weeks=weeks))

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
