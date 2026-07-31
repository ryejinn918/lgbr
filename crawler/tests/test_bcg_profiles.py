"""BCG profile allowlist guards."""

from __future__ import annotations

import pytest

from crawler.sources.bcg_browser import (
    LIST_URL,
    get_profile,
    is_allowlisted_list_url,
    is_publication_article_url,
    normalize_list_url,
)


def test_report_profile_includes_publications() -> None:
    prof = get_profile("report")
    assert LIST_URL in prof.list_urls
    assert is_allowlisted_list_url(LIST_URL, prof)
    assert is_allowlisted_list_url(LIST_URL + "/", prof)


def test_unknown_profile_raises() -> None:
    with pytest.raises(ValueError, match="unknown BCG profile"):
        get_profile("not-a-theme")


def test_theme_profiles_have_confirmed_surfaces() -> None:
    for pid in (
        "ai",
        "datacenter",
        "physical_ai",
        "appliance",
        "display",
        "automotive",
        "petrochemical",
    ):
        prof = get_profile(pid)
        assert prof.list_urls
        for url in prof.list_urls:
            assert url.startswith("https://www.bcg.com/")
            assert is_allowlisted_list_url(url, prof)


def test_random_list_url_not_allowlisted() -> None:
    prof = get_profile("ai")
    assert not is_allowlisted_list_url(
        "https://www.bcg.com/industries/made-up-industry", prof
    )


def test_publication_article_url_guard() -> None:
    assert is_publication_article_url(
        "https://www.bcg.com/publications/2026/building-business-value-with-ai-investment"
    )
    assert not is_publication_article_url(
        "https://www.bcg.com/industries/automotive/overview"
    )
    assert not is_publication_article_url(
        "https://www.bcg.com/publications"
    )


def test_normalize_list_url() -> None:
    assert normalize_list_url("https://www.bcg.com/publications/") == (
        "https://www.bcg.com/publications"
    )
