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
    requires_login: bool = False
    login_url: str | None = None


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
    "deloitte": SourceDef(
        id="deloitte",
        label="Deloitte",
        abbrev="dl",
        hub_url="https://www.deloitte.com/us/en/insights.html",
        has_search=True,
    ),
    "hbrkorea": SourceDef(
        id="hbrkorea",
        label="HBR Korea",
        abbrev="hk",
        hub_url="https://www.hbrkorea.com/",
        has_search=False,
        requires_login=True,
        login_url="https://www.hbrkorea.com/member/login",
    ),
}

FNGUIDE_MODES = frozenset(
    {
        "auto",
        "adhoc",
        "ai",
        "datacenter",
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


def source_requires_login(mode: str | None) -> bool:
    key = (mode or "").strip().lower()
    src = SOURCES.get(key)
    return bool(src and src.requires_login)


def valid_crawl_modes() -> frozenset[str]:
    return FNGUIDE_MODES | adhoc_source_ids()


def no_account_modes() -> frozenset[str]:
    """Modes that skip fnguide_sessions guard (no-login media adhoc)."""
    return frozenset(s.id for s in SOURCES.values() if not s.requires_login)


def cdp_modes() -> frozenset[str]:
    return frozenset({"adhoc"}) | adhoc_source_ids()


def source_mode_abbrev() -> dict[str, str]:
    return {s.id: s.abbrev for s in SOURCES.values()}
