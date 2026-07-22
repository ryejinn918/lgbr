"""Per-crawl download asset identifiers (kept in sync with crawler.asset_id)."""

from __future__ import annotations

import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

_SEOUL = ZoneInfo("Asia/Seoul")

MODE_ABBREV = {
    "datacenter": "dc",
    "ai": "ai",
    "physical_ai": "pai",
    "adhoc": "ad",
    "auto": "au",
}
LIMITED_MODES = frozenset({"datacenter", "ai", "physical_ai"})


def make_asset_id(
    mode: str,
    *,
    report_limit: int | None = None,
    when: datetime | None = None,
    suffix: str | None = None,
) -> str:
    """Build a short folder id: fn-dc-n20-250723-a1b2c3 / fn-ai-n30-…."""
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
        if report_limit is None:
            raise ValueError(f"report_limit required for {mode} asset_id")
        return f"fn-{abbrev}-n{int(report_limit)}-{day}-{token}"
    return f"fn-{abbrev}-{day}-{token}"
