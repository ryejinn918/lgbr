"""Unit tests for HBR date parsing helpers."""

from __future__ import annotations

from datetime import date

from crawler.sources.hbr_browser import (
    is_weak_link_title,
    looks_paywalled,
    parse_article_url,
    parse_publish_date,
    title_from_slug,
)


def test_title_from_slug_humanizes() -> None:
    assert (
        title_from_slug("bring-back-managing-for-value")
        == "bring back managing for value"
    )


def test_is_weak_link_title() -> None:
    assert is_weak_link_title("Read more")
    assert is_weak_link_title("ab")
    assert not is_weak_link_title("Bring Back Managing for Value")


def test_looks_paywalled_ignores_executive_agenda() -> None:
    assert not looks_paywalled(
        "HBR Executive Agenda Crafting Strategy in the Age of AI "
        "by Adi Ignatius Summary. In this issue of the HBR Executive Agenda"
    )
    assert looks_paywalled("Subscribe to read the full article")
    assert looks_paywalled("Already a subscriber? Sign in to read")
    assert looks_paywalled("Subscribe to HBR Executive for full access")
    assert not looks_paywalled("member benefits for HBR readers")


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
