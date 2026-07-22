"""Persist crawl runs in Postgres (parent of account sessions)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from crawler.db import CRAWL_STATE_LABELS, connect

TERMINAL_STATES = frozenset({"ended", "error"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_crawl(*, pid: int | None = None) -> dict[str, Any]:
    now = _now()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO fnguide_crawls (started_at, pid, state)
                VALUES (%s, %s, 'starting')
                RETURNING *
                """,
                (now, pid if pid is not None else os.getpid()),
            )
            row = dict(cur.fetchone())
        conn.commit()
    return _serialize(row)


def claim_crawl(crawl_id: UUID | str) -> dict[str, Any]:
    """Attach this process to an existing starting crawl created by the API."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fnguide_crawls
                SET pid = %s
                WHERE id = %s
                  AND ended_at IS NULL
                  AND state = 'starting'
                RETURNING *
                """,
                (os.getpid(), str(crawl_id)),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"No starting crawl {crawl_id}")
        conn.commit()
    return _serialize(dict(row))


def attach_session(crawl_id: UUID | str, session_id: UUID | str) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fnguide_crawls
                SET session_id = %s, pid = %s
                WHERE id = %s AND ended_at IS NULL
                RETURNING *
                """,
                (str(session_id), os.getpid(), str(crawl_id)),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"No open crawl {crawl_id}")
        conn.commit()
    return _serialize(dict(row))


def mark_active(crawl_id: UUID | str) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fnguide_crawls
                SET state = 'active', pid = %s
                WHERE id = %s
                  AND ended_at IS NULL
                  AND state = 'starting'
                  AND session_id IS NOT NULL
                RETURNING *
                """,
                (os.getpid(), str(crawl_id)),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(
                    f"Cannot mark active: crawl {crawl_id} not starting with session"
                )
        conn.commit()
    return _serialize(dict(row))


def mark_stopping(crawl_id: UUID | str, message: str | None = None) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fnguide_crawls
                SET state = 'stopping',
                    pid = %s,
                    message = COALESCE(%s, message)
                WHERE id = %s
                  AND ended_at IS NULL
                  AND state IN ('starting', 'active', 'stopping')
                RETURNING *
                """,
                (os.getpid(), message, str(crawl_id)),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"No open crawl {crawl_id} to mark stopping")
        conn.commit()
    return _serialize(dict(row))


def end_crawl(
    crawl_id: UUID | str,
    *,
    message: str | None = None,
    error: bool = False,
) -> dict[str, Any]:
    """Terminal transition. error=True → state=error; else ended."""
    now = _now()
    state = "error" if error else "ended"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fnguide_crawls
                SET state = %s,
                    ended_at = COALESCE(ended_at, %s),
                    message = COALESCE(%s, message)
                WHERE id = %s
                RETURNING *
                """,
                (state, now, message, str(crawl_id)),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"Crawl {crawl_id} not found for terminal end")
        conn.commit()
    return _serialize(dict(row))


def get_open_crawl() -> dict[str, Any] | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM fnguide_crawls
                WHERE ended_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
    return _serialize(dict(row)) if row else None


def get_latest_blocking_error() -> dict[str, Any] | None:
    """Newest crawl is error → block restart until cleared in DB."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM fnguide_crawls
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
    if not row or row.get("state") != "error":
        return None
    return _serialize(dict(row))


def get_crawl(crawl_id: UUID | str) -> dict[str, Any] | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM fnguide_crawls WHERE id = %s",
                (str(crawl_id),),
            )
            row = cur.fetchone()
    return _serialize(dict(row)) if row else None


def request_stop() -> dict[str, Any] | None:
    now = _now()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fnguide_crawls
                SET stop_requested_at = %s
                WHERE id = (
                    SELECT id FROM fnguide_crawls
                    WHERE ended_at IS NULL
                    ORDER BY started_at DESC
                    LIMIT 1
                )
                AND stop_requested_at IS NULL
                RETURNING *
                """,
                (now,),
            )
            row = cur.fetchone()
            if not row:
                cur.execute(
                    """
                    SELECT * FROM fnguide_crawls
                    WHERE ended_at IS NULL
                    ORDER BY started_at DESC
                    LIMIT 1
                    """
                )
                existing = cur.fetchone()
                conn.commit()
                return _serialize(dict(existing)) if existing else None
        conn.commit()
    return _serialize(dict(row))


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            out[key] = value.isoformat()
        elif isinstance(value, UUID):
            out[key] = str(value)
        else:
            out[key] = value
    state = out.get("state")
    out["label"] = CRAWL_STATE_LABELS.get(str(state), "종료")
    out["terminal"] = str(state) in TERMINAL_STATES or out.get("ended_at") is not None
    return out
