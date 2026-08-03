"""Themes display resolution for report chips."""

from __future__ import annotations

from lgbr_api.reports import _themes_from_attrs


def test_explicit_empty_themes_skips_crawl_profile_fallback() -> None:
    assert (
        _themes_from_attrs(
            {"themes": [], "crawl_profile": "ai", "theme": "datacenter"}
        )
        == []
    )


def test_explicit_themes_used() -> None:
    assert _themes_from_attrs({"themes": ["ai"], "crawl_profile": "datacenter"}) == [
        "ai"
    ]


def test_missing_themes_falls_back_to_crawl_profile() -> None:
    assert _themes_from_attrs({"crawl_profile": "ai"}) == ["ai"]
