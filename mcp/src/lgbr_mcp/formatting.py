"""SERP / tool payload shaping — original URL ok, no PDF bytes or download links."""

from __future__ import annotations

import json
from typing import Any

_SUMMARY_CLIP = 400

_STRIP_FILE_KEYS = ("file_path", "file_name", "pdf_url")

_DETAIL_META_KEYS = (
    "id",
    "title",
    "source",
    "provider",
    "published_at",
    "page_count",
    "themes",
    "url",
    "quality",
)


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)


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


def _themes(report: dict[str, Any], qj: dict[str, Any] | None = None) -> list[Any] | None:
    themes = report.get("themes")
    if isinstance(themes, list) and themes:
        return themes
    if qj and isinstance(qj.get("themes"), list) and qj["themes"]:
        return qj["themes"]
    theme = report.get("theme")
    if theme:
        return [theme]
    return None


def serp_item(report: dict[str, Any]) -> dict[str, Any]:
    clean = sanitize_report(report)
    qj = report.get("quality_json") if isinstance(report.get("quality_json"), dict) else {}
    item: dict[str, Any] = {
        "id": clean.get("id"),
        "title": clean.get("title"),
        "source": clean.get("source"),
        "provider": clean.get("provider"),
        "published_at": clean.get("published_at"),
        "page_count": clean.get("page_count"),
        "themes": _themes(clean, qj),
        "url": clean.get("url"),
        "quality": clean.get("quality"),
    }
    short = qj.get("short_title")
    if short:
        item["short_title"] = short
    kind = audit_kind_for_source(clean.get("source"))
    if kind == "sell_side":
        summary = _clip(qj.get("framework_summary") or qj.get("summary"))
    else:
        summary = _clip(qj.get("summary") or qj.get("framework_summary"))
    if summary:
        item["summary"] = summary
    return {k: v for k, v in item.items() if v is not None}


def serp_list_payload(result: dict[str, Any]) -> dict[str, Any]:
    items = [serp_item(r) for r in (result.get("items") or []) if isinstance(r, dict)]
    out: dict[str, Any] = {
        "ok": result.get("ok", True),
        "total": result.get("total"),
        "limit": result.get("limit"),
        "offset": result.get("offset"),
        "items": items,
        "hint": "For briefings: get_report(id) on quality=pass items (quality_json summary). No PDF.",
    }
    message = result.get("message")
    if message:
        out["message"] = message
    return out


def _slim_quality_json(qj: dict[str, Any], *, kind: str) -> dict[str, Any]:
    slim: dict[str, Any] = {}
    short = qj.get("short_title")
    if short:
        slim["short_title"] = short
    themes = qj.get("themes")
    if isinstance(themes, list) and themes:
        slim["themes"] = themes
    if kind == "sell_side":
        for key in ("topic", "framework_summary", "rationale"):
            val = qj.get(key)
            if val not in (None, "", [], {}):
                slim[key] = val
        return slim
    summary = qj.get("summary")
    framework = qj.get("framework_summary")
    if summary:
        slim["summary"] = summary
        if framework and framework != summary:
            slim["framework_summary"] = framework
    elif framework:
        slim["summary"] = framework
    return slim


def report_detail_payload(result: dict[str, Any]) -> dict[str, Any]:
    if not result.get("ok"):
        return result
    report = result.get("report")
    if not isinstance(report, dict):
        return result
    clean = sanitize_report(report)
    kind = audit_kind_for_source(clean.get("source"))
    qj_raw = clean.get("quality_json") if isinstance(clean.get("quality_json"), dict) else {}
    slim: dict[str, Any] = {k: clean.get(k) for k in _DETAIL_META_KEYS}
    themes = _themes(clean, qj_raw)
    if themes is not None:
        slim["themes"] = themes
    else:
        slim.pop("themes", None)
    if qj_raw:
        slim["quality_json"] = _slim_quality_json(qj_raw, kind=kind)
    flag = extract_truncated_flag(qj_raw.get("extract")) if qj_raw else None
    if flag is not None:
        slim["extract_truncated"] = flag
    slim = {k: v for k, v in slim.items() if v is not None}
    return {
        "ok": True,
        "report": slim,
        "hint": "Brief/cite: quality_json.summary (or short_title) + report.url. No PDF.",
    }
