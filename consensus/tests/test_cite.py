"""Unit tests for human cite labels."""

from __future__ import annotations

from datetime import date, datetime

from consensus.cite import (
    HUMAN_CITE_RULE,
    footnote_label,
    format_published_at,
    human_doc_header,
    short_provider,
    short_report_title,
)


def test_short_provider_strips_suffix():
    assert short_provider("KB투자증권") == "KB"
    assert short_provider("미래에셋증권") == "미래에셋"
    assert short_provider("DS") == "DS"


def test_short_report_title_clips():
    assert short_report_title("짧은제목") == "짧은제목"
    long = "가" * 40
    out = short_report_title(long, max_len=28)
    assert len(out) <= 28
    assert out.endswith("…")


def test_format_published_at():
    assert format_published_at(None) == ""
    assert format_published_at(date(2026, 6, 12)) == "2026-06-12"
    assert format_published_at(datetime(2026, 6, 12, 15, 0)) == "2026-06-12"
    assert format_published_at("2026-06-12T09:00:00+09:00") == "2026-06-12"


def test_human_doc_header():
    assert human_doc_header(provider="KB증권", title="정유 Monthly") == "KB | 정유 Monthly"
    assert (
        human_doc_header(
            provider="KB",
            title="정유",
            published_at="2026-06-12",
            page_start=12,
            page_end=14,
        )
        == "KB | 정유 | 2026-06-12 | 12–14쪽"
    )


def test_human_cite_rule_square_brackets():
    assert "provider" in HUMAN_CITE_RULE
    assert "short_title" in HUMAN_CITE_RULE
    assert "published_at" in HUMAN_CITE_RULE
    assert "Always lead with provider" in HUMAN_CITE_RULE
    assert "[provider] alone is fine" in HUMAN_CITE_RULE
    assert "square brackets" in HUMAN_CITE_RULE
    assert "Do not cite short_title alone" in HUMAN_CITE_RULE
    assert "report_id" in HUMAN_CITE_RULE


def test_footnote_label_square_brackets():
    assert footnote_label(provider="KB증권", title="정유 Monthly") == "[KB, 정유 Monthly]"
    assert (
        footnote_label(
            provider="IBK",
            title="x",
            short_title="자동차/2차전지 Monthly",
            published_at="2026-06-12",
        )
        == "[IBK, 자동차/2차전지 Monthly, 2026-06-12]"
    )
