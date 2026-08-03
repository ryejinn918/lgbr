"""Unit tests for HBR date parsing helpers."""

from __future__ import annotations

from datetime import date

from crawler.sources.hbr_browser import parse_article_url, parse_publish_date


def test_parse_article_url_uses_month_day_one() -> None:
    parsed = parse_article_url(
        "https://hbr.org/2026/07/ai-and-it-teams-often-clash-but-they-dont-have-to"
    )
    assert parsed is not None
    slug, pub = parsed
    assert slug == "ai-and-it-teams-often-clash-but-they-dont-have-to"
    assert pub == date(2026, 7, 1)


def test_parse_publish_date_long_form() -> None:
    assert parse_publish_date("July 31, 2026") == date(2026, 7, 31)
    assert parse_publish_date(
        "by Graham Kenny\n\nJuly 31, 2026\nAndriy Onufriyenko"
    ) == date(2026, 7, 31)


def test_parse_publish_date_iso() -> None:
    assert parse_publish_date("2026-07-31T12:00:00Z") == date(2026, 7, 31)
    assert parse_publish_date("2026-06-22") == date(2026, 6, 22)


def test_parse_publish_date_empty() -> None:
    assert parse_publish_date("") is None
    assert parse_publish_date("no date here") is None
