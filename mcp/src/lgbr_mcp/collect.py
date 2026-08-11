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
from lgbr_mcp.consensus import CONSENSUS_THEMES, CONSENSUS_THEMES_KO
from lgbr_mcp.formatting import dumps, report_detail_payload, serp_list_payload

COLLECT_SOURCES = (
    "fnguide, pwc, accenture, kpmg, ey, deloitte, "
    "hbr, hbrkorea, bain, mckinsey, bcg"
)

COLLECT_INSTRUCTIONS = f"""\
LGBR paid literature corpus (in-house, read-only).
Prefer for paywalled/subscription items (HBR, FnGuide, …) plus Korean summaries
(quality_json). No PDF bytes.

When web search is better: recent open consulting pages (kpmg, ey, …) — corpus
discovery can lag the public site. If a public URL is missing here, use web, then
re-check for a summary after ingest.

Routing: trend asks on covered themes ({CONSENSUS_THEMES}; {CONSENSUS_THEMES_KO})
→ prefer lgbr-consensus.get_consensus once as background, then search here for
lists/citations. search_reports first only for HBR-only briefs or explicit document
search without sector synthesis.
Tips: filter media with source ({COLLECT_SOURCES}). Brief with quality=pass → get_report.
Unaudited latest titles only: pending/all.
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
        title="LGBR Literature Corpus",
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
        """Search LGBR paid literature corpus (HBR, consulting, FnGuide, …).

        Better than web search: paywalled/subscription items; Korean summary,
        published_at, and source are normalized.
        When web is better: latest open consulting (kpmg, ey, …) — discovery can lag;
        if a public article is missing, use web then re-check corpus for summary.
        Covered-theme trend asks (동향): prefer lgbr-consensus.get_consensus(theme=…)
        once as background, then search here (증권사: source=fnguide and/or provider).
        Tips: set source for a medium (e.g. hbr; q alone often returns 0). Brief with
        quality=pass → get_report. Unaudited latest titles: pending/all. Sort published_at.
        No PDF bytes.

        Args:
            theme: ai, datacenter, macroeconomy, physical_ai, appliance, display, automotive, petrochemical
                (AI, 데이터센터, 거시경제, 피지컬 AI, 가전, 디스플레이, 자동차, 석유화학)
            q: title/keyword/summary search
            source: fnguide, pwc, accenture, kpmg, ey, deloitte, hbr, hbrkorea, bain, mckinsey, bcg
            provider: house/broker (partial match)
            quality: pass (default; has summary), pending, all, fail, unauditable
            sort: published_at (default), page_count, last_seen_at
            limit: default 10, max 200
            offset: page offset
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
        """Report detail: quality_json (Korean summary/themes or FnGuide audit) + source url. No PDF.

        Better than web search: in-house pre-summary/audit without reopening the paywall.
        If the piece is not in the corpus yet (common for open consulting), use web first.
        Tip: pending may lack summary — prefer pass for briefings.

        Args:
            report_id: id from search_reports
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
        """Breaking-news corpus search (secondary). Use search_reports for HBR/consulting.

        Args:
            q: title/url/publisher search
            source: all or arg
            has_body: all, yes, no
            include_body: include body_text when True
            limit: default 10
            offset: page offset
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
                "hint": "Article page is url. Set include_body=True for body text.",
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
