"""Per-crawl download asset identifiers (kept in sync with crawler.asset_id)."""

from __future__ import annotations

import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

_SEOUL = ZoneInfo("Asia/Seoul")

def _mode_abbrev() -> dict[str, str]:
    from lgbr_api.source_registry import source_mode_abbrev

    base = {
        # Legacy crawl folders (fn-dc-*); not an active search mode.
        "datacenter": "dc",
        "ai": "ai",
        "physical_ai": "pai",
        "appliance": "ap",
        "display": "dp",
        "automotive": "am",
        "petrochemical": "pc",
        "adhoc": "ad",
        "auto": "au",
    }
    base.update(source_mode_abbrev())
    return base


MODE_ABBREV = _mode_abbrev()
LIMITED_MODES = frozenset(
    {
        "ai",
        "physical_ai",
        "appliance",
        "display",
        "automotive",
        "petrochemical",
    }
)


def make_asset_id(
    mode: str,
    *,
    period_months: int | None = None,
    report_limit: int | None = None,
    when: datetime | None = None,
    suffix: str | None = None,
) -> str:
    """Build a short folder id: fn-dc-m3-250723-a1b2c3 (period) or legacy n{limit}."""
    abbrev = MODE_ABBREV.get(mode)
    if abbrev is None:
        raise ValueError(f"Invalid crawl mode for asset_id: {mode}")
    ts = when or datetime.now(_SEOUL)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=_SEOUL)
    else:
        ts = ts.astimezone(_SEOUL)
    day = ts.strftime("%y%m%d")
    token = suffix if suffix is not None else secrets.token_hex(3)
    if mode in LIMITED_MODES:
        if period_months is not None:
            return f"fn-{abbrev}-m{int(period_months)}-{day}-{token}"
        if report_limit is not None:
            return f"fn-{abbrev}-n{int(report_limit)}-{day}-{token}"
        raise ValueError(f"period_months required for {mode} asset_id")
    return f"fn-{abbrev}-{day}-{token}"
