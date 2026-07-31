"""Adhoc media source registry (source of truth for CDP hold sources).

Keep api ``lgbr_api/source_registry.py`` and FE ``mediaSources.ts`` in sync
when adding a source. Search automation (HTTP jobs) is per-source and separate.
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


# Add new adhoc media here; no DB migration needed for mode allowlist.
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
    "mckinsey": SourceDef(
        id="mckinsey",
        label="McKinsey",
        abbrev="mk",
        hub_url="https://www.mckinsey.com/",
        has_search=False,
    ),
    "bain": SourceDef(
        id="bain",
        label="Bain",
        abbrev="bn",
        hub_url="https://www.bain.com/",
        has_search=True,
    ),
    "hbrkorea": SourceDef(
        id="hbrkorea",
        label="HBR Korea",
        abbrev="hk",
        hub_url="https://www.hbrkorea.com/",
        has_search=True,
        requires_login=True,
        login_url="https://www.hbrkorea.com/member/login",
    ),
    "nikkei": SourceDef(
        id="nikkei",
        label="Nikkei",
        abbrev="nk",
        hub_url="https://www.nikkei.com/",
        has_search=False,
        requires_login=True,
        login_url="https://www.nikkei.com/login",
    ),
    "nikkeixtech": SourceDef(
        id="nikkeixtech",
        label="Nikkei xTECH",
        abbrev="xt",
        hub_url="https://xtech.nikkei.com/",
        has_search=False,
        requires_login=True,
        login_url=(
            "https://bpsso.nikkei.com/ep/auth/prev/?ts=nxt&ru="
            "https%3A%2F%2Fbpsso.nikkei.com%2Fep%2Fcookie%2F%3Fru%3D"
            "https%253A%252F%252Fxtech.nikkei.com%252F"
        ),
    ),
}


def get_source(source_id: str) -> SourceDef:
    key = (source_id or "").strip().lower()
    src = SOURCES.get(key)
    if src is None:
        raise ValueError(
            f"unknown adhoc source {source_id!r}; "
            f"expected one of: {', '.join(sorted(SOURCES))}"
        )
    return src


def adhoc_source_ids() -> frozenset[str]:
    return frozenset(SOURCES)


def is_adhoc_source(mode: str | None) -> bool:
    return (mode or "").strip().lower() in SOURCES


def source_requires_login(mode: str | None) -> bool:
    key = (mode or "").strip().lower()
    src = SOURCES.get(key)
    return bool(src and src.requires_login)


def no_account_source_ids() -> frozenset[str]:
    return frozenset(s.id for s in SOURCES.values() if not s.requires_login)


def source_mode_abbrev() -> dict[str, str]:
    return {s.id: s.abbrev for s in SOURCES.values()}
