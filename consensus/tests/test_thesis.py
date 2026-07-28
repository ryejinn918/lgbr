"""Unit tests for thesis cut parsing (no LLM)."""

from __future__ import annotations

import pytest

from consensus.thesis import parse_thesis_cut, thesis_system_prompt


def test_thesis_system_forbids_report_pick():
    prompt = thesis_system_prompt("automotive")
    assert "Do NOT choose which reports" in prompt
    assert "thesis" in prompt
    assert "pillar_sketch" in prompt


def test_parse_thesis_cut_ok():
    out = parse_thesis_cut(
        {
            "thesis": "수요는 지역·파워트레인으로 갈린다.",
            "cut_logic": "HEV와 BEV 신호가 달라 분리한다.",
            "pillar_sketch": ["축1", "축2", "축3"],
        }
    )
    assert out["thesis"].startswith("수요는")
    assert len(out["pillar_sketch"]) == 3


def test_parse_thesis_cut_requires_pillars():
    with pytest.raises(RuntimeError):
        parse_thesis_cut({"thesis": "x", "cut_logic": "y", "pillar_sketch": ["하나만"]})
