"""MCP report payload shaping — URL ok, no PDF fields, slim briefing schema."""

from __future__ import annotations

from lgbr_mcp.formatting import (
    extract_truncated_flag,
    report_detail_payload,
    serp_item,
    serp_list_payload,
)


def test_serp_summary_kind_keeps_url_no_pdf() -> None:
    report = {
        "id": "11111111-1111-1111-1111-111111111111",
        "title": "Sample",
        "source": "hbr",
        "has_file": True,
        "file_path": "/secret/x.pdf",
        "file_name": "x.pdf",
        "url": "https://hbr.org/2026/07/sample",
        "themes": ["ai"],
        "quality": "pass",
        "quality_json": {
            "short_title": "샘플요약",
            "summary": "A" * 500,
            "themes": ["ai"],
        },
    }
    item = serp_item(report)
    assert item["url"] == "https://hbr.org/2026/07/sample"
    assert item["short_title"] == "샘플요약"
    assert item["summary"] and item["summary"].endswith("…")
    assert "audit_kind" not in item
    assert "has_file" not in item
    assert "pdf_url" not in item
    assert "file_path" not in item
    assert "file_name" not in item


def test_serp_sell_side_uses_unified_summary() -> None:
    report = {
        "id": "22222222-2222-2222-2222-222222222222",
        "title": "Note",
        "source": "fnguide",
        "has_file": True,
        "url": "https://example.com/note",
        "quality_json": {
            "short_title": "인용제목",
            "topic": "주제",
            "framework_summary": "틀요약",
        },
    }
    item = serp_item(report)
    assert item["summary"] == "틀요약"
    assert "topic" not in item
    assert "framework_summary" not in item
    assert "audit_kind" not in item
    assert "pdf_url" not in item


def test_detail_strips_pdf_and_ops() -> None:
    result = {
        "ok": True,
        "report": {
            "id": "33333333-3333-3333-3333-333333333333",
            "source": "bain",
            "url": "https://www.bain.com/x",
            "file_path": "/nope.pdf",
            "file_name": "nope.pdf",
            "crawl_id": "c1",
            "quality_model": "x",
            "quality_json": {"summary": "요약", "framework_summary": "요약"},
        },
    }
    out = report_detail_payload(result)
    assert out["ok"] is True
    report = out["report"]
    assert report["url"] == "https://www.bain.com/x"
    assert "file_path" not in report
    assert "pdf_url" not in report
    assert "crawl_id" not in report
    assert "quality_model" not in report
    assert "audit_kind" not in report
    assert report["quality_json"]["summary"] == "요약"
    assert "framework_summary" not in report["quality_json"]
    assert "PDF" in out["hint"] or "pdf" in out["hint"].lower()


def test_list_hint_mentions_no_pdf() -> None:
    payload = serp_list_payload({"ok": True, "items": [], "total": 0})
    assert "PDF" in payload["hint"]
    assert "message" not in payload


def test_extract_truncated_flag() -> None:
    assert extract_truncated_flag(None) is None
    assert extract_truncated_flag({}) is None
    assert extract_truncated_flag({"truncated": 0}) == 0
    assert extract_truncated_flag({"truncated": 1}) == 1
    assert extract_truncated_flag({"truncated": True}) == 1
    assert extract_truncated_flag({"truncated": False}) == 0


def test_serp_omits_extract_truncated() -> None:
    report = {
        "id": "44444444-4444-4444-4444-444444444444",
        "title": "Long",
        "source": "accenture",
        "url": "https://www.accenture.com/x",
        "quality_json": {
            "summary": "요약",
            "extract": {"truncated": 1},
        },
    }
    item = serp_item(report)
    assert "extract_truncated" not in item
    assert item["summary"] == "요약"


def test_detail_extract_truncated_flag_only() -> None:
    result = {
        "ok": True,
        "report": {
            "id": "55555555-5555-5555-5555-555555555555",
            "source": "pwc",
            "url": "https://www.pwc.com/x",
            "quality_json": {
                "summary": "요약",
                "extract": {"truncated": 1},
                "pass": True,
                "confidence": 0.9,
            },
        },
    }
    out = report_detail_payload(result)
    assert out["report"]["extract_truncated"] == 1
    assert "extract" not in out["report"]["quality_json"]
    assert "pass" not in out["report"]["quality_json"]
    assert "quality_json" in out["hint"]


def test_detail_sell_side_keeps_topic_and_rationale() -> None:
    result = {
        "ok": True,
        "report": {
            "id": "66666666-6666-6666-6666-666666666666",
            "source": "fnguide",
            "title": "Note",
            "url": "https://example.com/note",
            "themes": ["physical_ai"],
            "quality": "pass",
            "quality_json": {
                "short_title": "짧은제목",
                "topic": "주제",
                "framework_summary": "틀",
                "rationale": "이유",
                "pass_signals": ["a", "b"],
                "extract": {"truncated": 0},
            },
        },
    }
    out = report_detail_payload(result)
    qj = out["report"]["quality_json"]
    assert qj["topic"] == "주제"
    assert qj["framework_summary"] == "틀"
    assert qj["rationale"] == "이유"
    assert "pass_signals" not in qj
    assert out["report"]["extract_truncated"] == 0
