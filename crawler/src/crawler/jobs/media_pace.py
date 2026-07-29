"""Shared item pacing for media list-while-download jobs.

Call after detail/PDF work; skip for list-only cutoffs that do no HTTP.
"""

from __future__ import annotations

import time

DEFAULT_ITEM_DELAY_SECONDS = 2.0
MIN_ITEM_DELAY_SECONDS = 0.0
MAX_ITEM_DELAY_SECONDS = 10.0


def clamp_item_delay_seconds(seconds: float) -> float:
    return max(
        MIN_ITEM_DELAY_SECONDS,
        min(float(seconds), MAX_ITEM_DELAY_SECONDS),
    )


def pace_after_item(seconds: float = DEFAULT_ITEM_DELAY_SECONDS) -> None:
    if seconds > 0:
        time.sleep(seconds)
