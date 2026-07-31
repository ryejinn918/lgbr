"""MCP report payload shaping — URL ok, no PDF fields."""

from __future__ import annotations

from lgbr_mcp.formatting import report_detail_payload, serp_item, serp_list_payload


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
    assert item["audit_kind"] == "summary"
    assert item["short_title"] == "샘플요약"
    assert item["summary"] and item["summary"].endswith("…")
    assert "pdf_url" not in item
    assert "file_path" not in item
    assert "file_name" not in item


def test_serp_sell_side_fields() -> None:
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
    assert item["audit_kind"] == "sell_side"
    assert item["topic"] == "주제"
    assert item["framework_summary"] == "틀요약"
    assert "summary" not in item
    assert "pdf_url" not in item


def test_detail_strips_pdf_keeps_url() -> None:
    result = {
        "ok": True,
        "report": {
            "id": "33333333-3333-3333-3333-333333333333",
            "source": "bain",
            "url": "https://www.bain.com/x",
            "file_path": "/nope.pdf",
            "file_name": "nope.pdf",
            "quality_json": {"summary": "요약"},
        },
    }
    out = report_detail_payload(result)
    assert out["ok"] is True
    assert out["report"]["url"] == "https://www.bain.com/x"
    assert out["report"]["audit_kind"] == "summary"
    assert "file_path" not in out["report"]
    assert "pdf_url" not in out["report"]
    assert "PDF" in out["hint"] or "pdf" in out["hint"].lower()


def test_list_hint_mentions_no_pdf() -> None:
    payload = serp_list_payload({"ok": True, "items": [], "total": 0})
    assert "PDF" in payload["hint"]
