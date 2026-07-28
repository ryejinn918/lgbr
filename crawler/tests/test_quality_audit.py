"""Unit tests for quality audit normalize (no LLM)."""

from __future__ import annotations

from crawler.quality_audit import normalize_result


def test_normalize_result_short_title():
    out = normalize_result(
        {
            "pass": True,
            "confidence": 0.9,
            "has_coherent_framework": True,
            "has_broad_sector_coverage": True,
            "scope": "sector",
            "topic": "석화 마진",
            "short_title": "  6월 석화 마진  ",
            "framework_summary": "요약",
            "fail_reasons": [],
            "pass_signals": ["ok"],
            "rationale": "통과",
        }
    )
    assert out["short_title"] == "6월 석화 마진"
    assert out["pass"] is True


def test_normalize_result_short_title_clips():
    out = normalize_result(
        {
            "pass": False,
            "confidence": 0.2,
            "has_coherent_framework": False,
            "has_broad_sector_coverage": False,
            "scope": "company",
            "topic": "x",
            "short_title": "가" * 40,
            "framework_summary": None,
            "fail_reasons": ["equity"],
            "pass_signals": [],
            "rationale": "거절",
        }
    )
    assert len(out["short_title"]) <= 28
    assert out["short_title"].endswith("…")


def test_normalize_result_missing_short_title():
    out = normalize_result(
        {
            "pass": False,
            "confidence": 0.1,
            "has_coherent_framework": False,
            "has_broad_sector_coverage": False,
            "scope": "unclear",
            "topic": "",
            "framework_summary": None,
            "fail_reasons": [],
            "pass_signals": [],
            "rationale": "",
        }
    )
    assert out["short_title"] == ""
