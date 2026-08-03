"""Unit tests for quality audit normalize (no LLM)."""

from __future__ import annotations

from crawler.quality_audit import (
    EMPTY_BODY_SUMMARY,
    MEDIA_SUMMARY_MAX_CHARS,
    PDF_PAGES,
    SUMMARY_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    apply_source_pass_policy,
    build_extract_meta,
    empty_body_quality_result,
    is_thin_body_text,
    normalize_for_source,
    normalize_media_result,
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
    raw = normalize_media_result(
        {
            "pass": False,
            "confidence": 0.2,
            "short_title": "종목 노트",
            "summary": "요약 유지",
            "themes": [],
        }
    )
    out = apply_source_pass_policy(raw, "pwc")
    assert out["pass"] is True
    assert out["short_title"] == "종목 노트"
    assert out["summary"] == "요약 유지"
    assert out["framework_summary"] == "요약 유지"
    assert "topic" not in out
    assert "fail_reasons" not in out


def test_system_prompt_for_source_splits_fnguide_vs_media():
    assert system_prompt_for_source("fnguide") is SYSTEM_PROMPT
    assert system_prompt_for_source("hbrkorea") is SUMMARY_SYSTEM_PROMPT
    assert system_prompt_for_source("pwc") is SUMMARY_SYSTEM_PROMPT
    assert "NOT a sell-side" in SUMMARY_SYSTEM_PROMPT
    assert '"summary"' in SUMMARY_SYSTEM_PROMPT
    assert "hierarchical" in SUMMARY_SYSTEM_PROMPT
    assert "framework_summary" not in SUMMARY_SYSTEM_PROMPT


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


def test_normalize_media_result_slim_and_sync():
    long_summary = "- 항목\n" + ("상세 내용. " * 200)
    out = normalize_media_result(
        {
            "pass": True,
            "confidence": 0.8,
            "short_title": "긴 보고 요약",
            "summary": long_summary,
            "themes": ["ai", "datacenter", "bogus", "macroeconomy"],
            "fail_reasons": ["should_drop"],
            "rationale": "should_drop",
            "topic": "should_drop",
        }
    )
    assert set(out.keys()) == {
        "pass",
        "confidence",
        "short_title",
        "summary",
        "framework_summary",
        "themes",
    }
    assert out["summary"] == out["framework_summary"]
    assert out["themes"] == ["ai", "datacenter"]
    assert len(out["summary"]) <= MEDIA_SUMMARY_MAX_CHARS


def test_normalize_media_result_falls_back_to_framework_summary():
    out = normalize_media_result(
        {
            "pass": True,
            "confidence": 0.5,
            "short_title": "인용",
            "framework_summary": "레거시 요약",
            "themes": [],
        }
    )
    assert out["summary"] == "레거시 요약"
    assert out["framework_summary"] == "레거시 요약"


def test_normalize_for_source_routes():
    media = normalize_for_source(
        {"pass": True, "confidence": 1, "short_title": "a", "summary": "요약"},
        "hbr",
    )
    assert "fail_reasons" not in media
    fg = normalize_for_source(
        {
            "pass": True,
            "confidence": 1,
            "has_coherent_framework": True,
            "has_broad_sector_coverage": True,
            "scope": "sector",
            "short_title": "b",
            "framework_summary": "요약",
            "fail_reasons": [],
            "pass_signals": [],
            "rationale": "ok",
        },
        "fnguide",
    )
    assert fg["pass"] is True
    assert "fail_reasons" in fg


def test_build_extract_meta_truncated_by_pages():
    meta = build_extract_meta(
        pages_total=61,
        truncated_by_chars=False,
        max_pages=PDF_PAGES,
    )
    assert meta == {"truncated": 1}


def test_build_extract_meta_full_short_pdf():
    meta = build_extract_meta(
        pages_total=3,
        truncated_by_chars=False,
        max_pages=PDF_PAGES,
    )
    assert meta == {"truncated": 0}


def test_build_extract_meta_char_cap():
    meta = build_extract_meta(
        pages_total=2,
        truncated_by_chars=True,
        max_pages=PDF_PAGES,
    )
    assert meta == {"truncated": 1}


def test_build_extract_meta_unknown_page_count():
    meta = build_extract_meta(
        pages_total=None,
        truncated_by_chars=False,
    )
    assert meta == {"truncated": 0}


def test_is_thin_body_text_empty_and_one_sentence():
    assert is_thin_body_text("") is True
    assert is_thin_body_text("   \n\t  ") is True
    assert is_thin_body_text("Banks are investing in AI.") is True
    assert is_thin_body_text("Banks are investing in AI") is True


def test_is_thin_body_text_two_sentences():
    assert (
        is_thin_body_text(
            "Banks are investing in AI. Contact centers still struggle."
        )
        is False
    )


def test_empty_body_quality_result_schema():
    out = empty_body_quality_result(extract={"truncated": 0})
    assert out["pass"] is False
    assert out["summary"] == EMPTY_BODY_SUMMARY
    assert out["framework_summary"] == EMPTY_BODY_SUMMARY
    assert out["themes"] == []
    assert out["empty_body"] is True
    assert out["short_title"] == ""
    assert out["extract"] == {"truncated": 0}
