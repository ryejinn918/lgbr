"""Tool descriptions stay short and tip-oriented for Claude connectors."""

from __future__ import annotations

import asyncio

from lgbr_mcp.collect import build_collect_server
from lgbr_mcp.consensus import build_consensus_server


def _tool_map(server) -> dict[str, str]:
    tools = asyncio.run(server.list_tools())
    return {t.name: (t.description or "") for t in tools}


def test_search_reports_has_practical_tips() -> None:
    desc = _tool_map(build_collect_server())["search_reports"]
    assert "LG MRI" in desc or "paid" in desc.lower()
    assert "Better than web search" in desc or "web search" in desc.lower()
    assert "When web is better" in desc or "kpmg" in desc.lower()
    assert "source" in desc and "hbr" in desc
    assert "pass" in desc and "get_report" in desc
    assert "get_consensus" in desc
    assert "FIRST" in desc and "background" in desc.lower()
    assert len(desc) < 1600


def test_get_report_notes_pending_gap() -> None:
    desc = _tool_map(build_collect_server())["get_report"]
    assert "Better than web search" in desc or "web search" in desc.lower()
    assert "quality_json" in desc
    assert "pending" in desc
    assert len(desc) < 900


def test_get_consensus_points_collect_for_articles() -> None:
    desc = _tool_map(build_consensus_server())["get_consensus"]
    assert "LG MRI" in desc
    assert "Better than web search" in desc or "web search" in desc.lower()
    assert "search_reports" in desc
    assert "FIRST" in desc and "background" in desc.lower()
    assert "physical_ai" in desc
    assert "axes + frame" in desc or "frame" in desc.lower()
    assert "consensus_frame" not in desc
    assert "filled_frame" not in desc
    assert len(desc) < 700
