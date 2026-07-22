"""Bot-declared session status written to `.fnsearch/status.json`."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

StatusState = Literal["idle", "logging_in", "active", "logging_out", "error"]

DEFAULT_STATUS_PATH = Path(".fnsearch/status.json")

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def idle_status() -> dict[str, Any]:
    return dict(_IDLE)


def get_status(path: Path = DEFAULT_STATUS_PATH) -> dict[str, Any]:
    if not path.exists():
        return idle_status()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return idle_status()
    if not isinstance(data, dict):
        return idle_status()
    merged = idle_status()
    merged.update(data)
    return merged


def set_status(
    *,
    state: StatusState,
    user_id: str | None = None,
    started_at: str | None = None,
    current_url: str | None = None,
    step: str | None = None,
    message: str | None = None,
    path: Path = DEFAULT_STATUS_PATH,
    keep_started_at: bool = True,
) -> dict[str, Any]:
    previous = get_status(path) if keep_started_at else idle_status()
    if state == "idle":
        resolved_started_at = None
    elif started_at is not None:
        resolved_started_at = started_at
    elif keep_started_at and previous.get("started_at"):
        resolved_started_at = previous.get("started_at")
    else:
        resolved_started_at = _now_iso()

    payload: dict[str, Any] = {
        "state": state,
        "user_id": (
            None
            if state == "idle"
            else (user_id if user_id is not None else previous.get("user_id"))
        ),
        "started_at": resolved_started_at,
        "updated_at": _now_iso(),
        "pid": os.getpid() if state != "idle" else None,
        "current_url": None if state == "idle" else current_url,
        "step": None if state == "idle" else step,
        "message": message,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=".status-",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(raw)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)
    return payload


def clear_status(path: Path = DEFAULT_STATUS_PATH) -> dict[str, Any]:
    return set_status(state="idle", path=path, keep_started_at=False)
