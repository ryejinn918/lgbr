"""Adhoc media sources — keep in sync with crawler.sources.registry.

API validates crawl modes / asset abbrevs here because it does not import
the crawler package at runtime (worker is a subprocess).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceDef:
    id: str
    label: str
    abbrev: str
    hub_url: str
    has_search: bool = False


SOURCES: dict[str, SourceDef] = {
    "pwc": SourceDef(
        id="pwc",
        label="PwC",
        abbrev="pw",
        hub_url="https://www.pwc.com/kr/ko/insights.html",
        has_search=True,
    ),
    "accenture": SourceDef(
        id="accenture",
        label="Accenture",
        abbrev="ac",
        hub_url="https://www.accenture.com/us-en/insights",
        has_search=True,
    ),
    "kpmg": SourceDef(
        id="kpmg",
        label="KPMG",
        abbrev="kp",
        hub_url="https://kpmg.com/us/en/insights-and-resources.html",
        has_search=True,
    ),
    "ey": SourceDef(
        id="ey",
        label="EY",
        abbrev="ey",
        hub_url="https://www.ey.com/en_us/insights",
        has_search=True,
    ),
}

FNGUIDE_MODES = frozenset(
    {
        "auto",
        "adhoc",
        "ai",
        "physical_ai",
        "appliance",
        "display",
        "automotive",
        "petrochemical",
    }
)


def adhoc_source_ids() -> frozenset[str]:
    return frozenset(SOURCES)


def is_adhoc_source(mode: str | None) -> bool:
    return (mode or "").strip().lower() in SOURCES


def valid_crawl_modes() -> frozenset[str]:
    return FNGUIDE_MODES | adhoc_source_ids()


def no_account_modes() -> frozenset[str]:
    """Modes that skip fnguide_sessions guard."""
    return adhoc_source_ids()


def cdp_modes() -> frozenset[str]:
    return frozenset({"adhoc"}) | adhoc_source_ids()


def source_mode_abbrev() -> dict[str, str]:
    return {s.id: s.abbrev for s in SOURCES.values()}
