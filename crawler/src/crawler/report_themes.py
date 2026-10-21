"""Report content themes vs crawl-profile mode ids."""

from __future__ import annotations

# Content classification (attrs.themes[]); multi-label, duplicates allowed.
REPORT_THEMES = frozenset(
    {
        "ai",
        "datacenter",
        "macroeconomy",
        "physical_ai",
        "appliance",
        "display",
        "automotive",
        "petrochemical",
    }
)

# FnGuide / Deloitte search-profile modes (attrs.crawl_profile).
CRAWL_PROFILE_MODES = frozenset(
    {
        "ai",
        "datacenter",
        "macroeconomy",
        "physical_ai",
        "appliance",
        "display",
        "automotive",
        "petrochemical",
    }
)

THEME_LABEL_KO = {
    "ai": "AI",
    "datacenter": "데이터센터",
    "macroeconomy": "거시경제",
    "physical_ai": "피지컬 AI",
    "appliance": "가전",
    "display": "디스플레이",
    "automotive": "자동차",
    "petrochemical": "석유화학",
}
