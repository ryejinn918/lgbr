"""Consensus themes must have reproducible FnGuide search profiles."""

from crawler.jobs.search_report import PROFILES, SEARCH_PROFILE_ORDER


def test_every_consensus_theme_has_search_profile():
    assert set(PROFILES) == {
        "ai",
        "datacenter",
        "macroeconomy",
        "physical_ai",
        "appliance",
        "display",
        "automotive",
        "petrochemical",
    }
    assert set(SEARCH_PROFILE_ORDER) == set(PROFILES)


def test_sparse_themes_use_sector_oriented_filters():
    assert PROFILES["macroeconomy"].sectors == ("금융",)
    assert PROFILES["appliance"].sectors == ("경기소비재",)
    assert PROFILES["display"].sectors == ("IT",)
    assert "가전 산업" in PROFILES["appliance"].keywords
    assert "디스플레이 산업" in PROFILES["display"].keywords