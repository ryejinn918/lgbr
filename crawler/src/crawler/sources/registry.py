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


def source_mode_abbrev() -> dict[str, str]:
    return {s.id: s.abbrev for s in SOURCES.values()}
