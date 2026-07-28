"""Per-crawl download asset identifiers and paths."""

from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


# Prefer repo-root .crawler/downloads (API worker cwd); fall back to CWD-relative.
def _default_downloads_root() -> Path:
    here = Path(__file__).resolve()
    # .../crawler/src/crawler/asset_id.py -> repo root is parents[3]
    for parent in here.parents:
        candidate = parent / ".crawler" / "downloads"
        if (parent / "crawler").is_dir() and (parent / "api").is_dir():
            return candidate
    return Path(".crawler/downloads")


DOWNLOADS_ROOT = _default_downloads_root()
_SEOUL = ZoneInfo("Asia/Seoul")

MODE_ABBREV = {
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
LIMITED_MODES = frozenset(
    {
        "datacenter",
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


def downloads_dir(asset_id: str, *, root: Path | None = None) -> Path:
    base = root if root is not None else DOWNLOADS_ROOT
    return base / asset_id
