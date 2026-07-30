"""SERP / tool payload shaping — links in, no PDF bytes."""

from __future__ import annotations

import json
from typing import Any

from lgbr_mcp.signed_urls import sign_report_pdf_url

_REPORT_BLOCKED_SOURCES = frozenset({"fnguide"})

_SERP_KEYS = (
    "id",
    "title",
    "source",
    "source_key",
    "provider",
    "published_at",
    "page_count",
    "themes",
    "theme",
    "quality",
    "quality_pass",
    "quality_scope",
    "status",
    "has_file",
)


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def source_url_for_report(report: dict[str, Any]) -> str | None:
    src = str(report.get("source") or "").strip().lower()
    if not src or src in _REPORT_BLOCKED_SOURCES:
        return None
    url = report.get("url")
    if not isinstance(url, str):
        return None
    u = url.strip()
    if u.startswith(("http://", "https://")):
        return u
    return None


def attach_report_links(report: dict[str, Any]) -> dict[str, Any]:
    out = dict(report)
    rid = str(out.get("id") or "").strip()
    if out.get("has_file") and rid:
        out["pdf_url"] = sign_report_pdf_url(rid)
    else:
        out["pdf_url"] = None
    out["source_url"] = source_url_for_report(out)
    return out


def serp_item(report: dict[str, Any]) -> dict[str, Any]:
    linked = attach_report_links(report)
    item = {k: linked.get(k) for k in _SERP_KEYS}
    item["pdf_url"] = linked.get("pdf_url")
    item["source_url"] = linked.get("source_url")
    # Short quality hint without full quality_json
    qj = report.get("quality_json")
    if isinstance(qj, dict):
        short = qj.get("short_title")
        topic = qj.get("topic")
        if short:
            item["short_title"] = short
        if topic:
            item["topic"] = topic
    return item


def serp_list_payload(result: dict[str, Any]) -> dict[str, Any]:
    items = [serp_item(r) for r in (result.get("items") or []) if isinstance(r, dict)]
    return {
        "ok": result.get("ok", True),
        "message": result.get("message"),
        "total": result.get("total"),
        "limit": result.get("limit"),
        "offset": result.get("offset"),
        "items": items,
        "hint": (
            "후보를 고른 뒤 get_report(id)로 품질 상세·링크를 보세요. "
            "동향 요약이 목표면 lgbr-consensus.get_consensus(theme)을 먼저."
        ),
    }


def report_detail_payload(result: dict[str, Any]) -> dict[str, Any]:
    if not result.get("ok"):
        return result
    report = result.get("report")
    if not isinstance(report, dict):
        return result
    linked = attach_report_links(report)
    return {
        "ok": True,
        "report": linked,
        "hint": (
            "품질 심사는 report.quality_json. "
            "원문 링크는 pdf_url/source_url(브라우저). "
            "섹터 프레임은 lgbr-consensus.get_consensus."
        ),
    }
