"""Unit tests for quality audit normalize (no LLM)."""

from __future__ import annotations

from crawler.quality_audit import (
    SUMMARY_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    apply_source_pass_policy,
    normalize_result,
    system_prompt_for_source,
)


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


def test_apply_source_pass_policy_keeps_fnguide_fail():
    raw = normalize_result(
        {
            "pass": False,
            "confidence": 0.2,
            "has_coherent_framework": False,
            "has_broad_sector_coverage": False,
            "scope": "company",
            "topic": "개별 종목",
            "short_title": "종목 노트",
            "framework_summary": "요약 유지",
            "fail_reasons": ["equity"],
            "pass_signals": [],
            "rationale": "거절",
        }
    )
    out = apply_source_pass_policy(raw, "fnguide")
    assert out["pass"] is False
    assert out["short_title"] == "종목 노트"
    assert out["framework_summary"] == "요약 유지"


def test_apply_source_pass_policy_forces_pwc_pass():
    raw = normalize_result(
        {
            "pass": False,
            "confidence": 0.2,
            "has_coherent_framework": False,
            "has_broad_sector_coverage": False,
            "scope": "company",
            "topic": "개별 종목",
            "short_title": "종목 노트",
            "framework_summary": "요약 유지",
            "fail_reasons": ["equity"],
            "pass_signals": [],
            "rationale": "거절",
        }
    )
    out = apply_source_pass_policy(raw, "pwc")
    assert out["pass"] is True
    assert out["short_title"] == "종목 노트"
    assert out["framework_summary"] == "요약 유지"
    assert out["topic"] == "개별 종목"


def test_system_prompt_for_source_splits_fnguide_vs_media():
    assert system_prompt_for_source("fnguide") is SYSTEM_PROMPT
    assert system_prompt_for_source("hbrkorea") is SUMMARY_SYSTEM_PROMPT
    assert system_prompt_for_source("pwc") is SUMMARY_SYSTEM_PROMPT
    assert "NOT a sell-side" in SUMMARY_SYSTEM_PROMPT
    assert "framework_summary" in SUMMARY_SYSTEM_PROMPT


def test_normalize_result_themes_multi():
    out = normalize_result(
        {
            "pass": True,
            "confidence": 0.9,
            "has_coherent_framework": True,
            "has_broad_sector_coverage": True,
            "scope": "sector",
            "topic": "AIDC",
            "short_title": "DC 전력",
            "framework_summary": "요약",
            "fail_reasons": [],
            "pass_signals": ["ok"],
            "rationale": "통과",
            "themes": ["ai", "datacenter", "bogus", "macroeconomy"],
        }
    )
    assert out["themes"] == ["ai", "datacenter", "macroeconomy"]
    assert out["pass"] is True
