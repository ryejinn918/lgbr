"""SERP / tool payload shaping — original URL ok, no PDF bytes or download links."""

from __future__ import annotations

import json
from typing import Any

_SUMMARY_CLIP = 400

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
    "url",
)

_STRIP_FILE_KEYS = ("file_path", "file_name", "pdf_url")


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def audit_kind_for_source(source: Any) -> str:
    if str(source or "").strip().lower() == "fnguide":
        return "sell_side"
    return "summary"


def _clip(text: Any, *, max_len: int = _SUMMARY_CLIP) -> str | None:
    s = " ".join(str(text or "").split())
    if not s:
        return None
    if len(s) > max_len:
        return s[: max_len - 1].rstrip() + "…"
    return s


def extract_truncated_flag(extract: Any) -> int | None:
    """Return 1/0 when extract.truncated is set; else None."""
    if not isinstance(extract, dict) or "truncated" not in extract:
        return None
    return 1 if extract.get("truncated") else 0


def sanitize_report(report: dict[str, Any]) -> dict[str, Any]:
    """Keep original web url; strip PDF path / download fields."""
    out = dict(report)
    for key in _STRIP_FILE_KEYS:
        out.pop(key, None)
    return out


def serp_item(report: dict[str, Any]) -> dict[str, Any]:
    clean = sanitize_report(report)
    item = {k: clean.get(k) for k in _SERP_KEYS}
    item["audit_kind"] = audit_kind_for_source(clean.get("source"))
    qj = report.get("quality_json")
    if not isinstance(qj, dict):
        return item
    short = qj.get("short_title")
    if short:
        item["short_title"] = short
    kind = item["audit_kind"]
    if kind == "sell_side":
        topic = qj.get("topic")
        if topic:
            item["topic"] = topic
        fw = _clip(qj.get("framework_summary"))
        if fw:
            item["framework_summary"] = fw
    else:
        summary = _clip(qj.get("summary") or qj.get("framework_summary"))
        if summary:
            item["summary"] = summary
    flag = extract_truncated_flag(qj.get("extract"))
    if flag is not None:
        item["extract_truncated"] = flag
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
            "후보 id로 get_report — 품질검사·요약 상세와 원문 url. "
            "PDF는 제공하지 않음. 동향 요약은 lgbr-consensus.get_consensus."
        ),
    }


def report_detail_payload(result: dict[str, Any]) -> dict[str, Any]:
    if not result.get("ok"):
        return result
    report = result.get("report")
    if not isinstance(report, dict):
        return result
    clean = sanitize_report(report)
    kind = audit_kind_for_source(clean.get("source"))
    clean["audit_kind"] = kind
    qj = clean.get("quality_json")
    if isinstance(qj, dict):
        flag = extract_truncated_flag(qj.get("extract"))
        if flag is not None:
            clean["extract_truncated"] = flag
    return {
        "ok": True,
        "report": clean,
        "hint": (
            "원문 웹 URL은 report.url. PDF·파일 경로는 제공하지 않음. "
            "summary(요약): quality_json.short_title / summary / themes. "
            "sell_side(fnguide): topic, framework_summary, fail_reasons, "
            "pass_signals, rationale. "
            "입력 절단은 extract_truncated(0/1). "
            "섹터 프레임은 lgbr-consensus.get_consensus."
        ),
    }
