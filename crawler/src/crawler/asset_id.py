"""Per-crawl download asset identifiers and paths."""

from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DOWNLOADS_ROOT = Path(".crawler/downloads")
_SEOUL = ZoneInfo("Asia/Seoul")

MODE_ABBREV = {
    "datacenter": "dc",
    "adhoc": "ad",
    "auto": "au",
}


def make_asset_id(
    mode: str,
    *,
    report_limit: int | None = None,
    when: datetime | None = None,
    suffix: str | None = None,
) -> str:
    """Build a short folder id: fn-dc-n20-250723-a1b2c3."""
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
    if mode == "datacenter":
        if report_limit is None:
            raise ValueError("report_limit required for datacenter asset_id")
        return f"fn-dc-n{int(report_limit)}-{day}-{token}"
    return f"fn-{abbrev}-{day}-{token}"


def downloads_dir(asset_id: str, *, root: Path | None = None) -> Path:
    base = root if root is not None else DOWNLOADS_ROOT
    return base / asset_id
