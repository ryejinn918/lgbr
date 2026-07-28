"""FS roots for slice/corpus cache (results live in DB)."""

from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_SEOUL = ZoneInfo("Asia/Seoul")

THEME_ABBREV = {
    # Legacy asset ids (cs-dc-*); not an active consensus theme.
    "datacenter": "dc",
    "ai": "ai",
    "physical_ai": "pai",
    "appliance": "ap",
    "display": "dp",
    "automotive": "am",
    "petrochemical": "pc",
}


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "crawler").is_dir() and (parent / "api").is_dir():
            return parent
    return Path.cwd()


CONSENSUS_ROOT = _repo_root() / ".consensus"


def make_asset_id(theme: str, *, when: datetime | None = None) -> str:
    abbrev = THEME_ABBREV.get(theme)
    if abbrev is None:
        raise ValueError(f"invalid theme: {theme}")
    ts = when or datetime.now(_SEOUL)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=_SEOUL)
    else:
        ts = ts.astimezone(_SEOUL)
    return f"cs-{abbrev}-{ts.strftime('%y%m%d')}-{secrets.token_hex(3)}"


def doc_cache_dir(report_id: str, content_hash: str) -> Path:
    return CONSENSUS_ROOT / "docs" / report_id / content_hash[:16]


def run_dir(asset_id: str) -> Path:
    return CONSENSUS_ROOT / "runs" / asset_id
