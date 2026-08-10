"""Nikkei section registry (wor.jp RSS mirrors of /news/category/).

Keep FE ``nikkeiSections.ts`` in sync when adding sections.
"""

from __future__ import annotations

from dataclasses import dataclass


RSS_BASE = "https://assets.wor.jp/rss/rdf/nikkei"
CATEGORY_BASE = "https://www.nikkei.com/news/category"


@dataclass(frozen=True)
class NikkeiSection:
    id: str
    label: str
    rss_url: str
    category_url: str


def _section(section_id: str, label: str, *, category_slug: str | None = None) -> NikkeiSection:
    slug = category_slug if category_slug is not None else section_id
    if slug == "":
        category_url = f"{CATEGORY_BASE}/"
    else:
        category_url = f"{CATEGORY_BASE}/{slug}/"
    return NikkeiSection(
        id=section_id,
        label=label,
        rss_url=f"{RSS_BASE}/{section_id}.rdf",
        category_url=category_url,
    )


# Confirmed HTTP 200 on assets.wor.jp (2026-08-10).
SECTIONS: dict[str, NikkeiSection] = {
    "news": _section("news", "速報", category_slug=""),
    "business": _section("business", "ビジネス"),
    "economy": _section("economy", "政治・経済"),
    "markets": _section("markets", "マーケット"),
    "technology": _section("technology", "テクノロジー"),
    "international": _section("international", "国際・アジア"),
    "sports": _section("sports", "スポーツ"),
    "society": _section("society", "社会"),
}

DEFAULT_SECTION = "economy"


def get_section(section_id: str | None) -> NikkeiSection:
    key = (section_id or DEFAULT_SECTION).strip().lower()
    sec = SECTIONS.get(key)
    if sec is None:
        raise ValueError(
            f"unknown nikkei section {section_id!r}; "
            f"expected one of: {', '.join(sorted(SECTIONS))}"
        )
    return sec


def section_ids() -> frozenset[str]:
    return frozenset(SECTIONS)
