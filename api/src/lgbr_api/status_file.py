"""Read bot status.json without depending on crawler."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_STATUS = _REPO_ROOT / ".crawler" / "status.json"

DEFAULT_STATUS_PATH = Path(
    os.environ.get("FNGUIDE_STATUS_PATH", str(_DEFAULT_STATUS))
)

_IDLE: dict[str, Any] = {
    "state": "idle",
    "user_id": None,
    "started_at": None,
    "updated_at": None,
    "pid": None,
    "current_url": None,
    "step": None,
    "message": None,
}


def idle_status() -> dict[str, Any]:
    return dict(_IDLE)


def read_status(path: Path | None = None) -> dict[str, Any]:
    status_path = path or DEFAULT_STATUS_PATH
    if not status_path.exists():
        return idle_status()
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return idle_status()
    if not isinstance(data, dict):
        return idle_status()
    merged = idle_status()
    merged.update(data)
    return merged
