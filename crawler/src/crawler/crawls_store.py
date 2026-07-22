"""Persist crawl runs in Postgres (parent of account sessions)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from crawler.asset_id import make_asset_id
from crawler.db import CRAWL_STATE_LABELS, connect

TERMINAL_STATES = frozenset({"ended", "error"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


VALID_MODES = frozenset({"auto", "adhoc", "datacenter"})


def create_crawl(
    *,
    pid: int | None = None,
    mode: str = "auto",
    report_limit: int = 5,
) -> dict[str, Any]:
    now = _now()
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid crawl mode: {mode}")
    if report_limit < 1 or report_limit > 50:
        raise ValueError(f"Invalid report_limit: {report_limit}")
    asset_id = make_asset_id(
        mode,
        report_limit=report_limit if mode == "datacenter" else None,
    )
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO fnguide_crawls
                    (started_at, pid, state, mode, report_limit, asset_id)
                VALUES (%s, %s, 'starting', %s, %s, %s)
                RETURNING *
                """,
                (
                    now,
                    pid if pid is not None else os.getpid(),
                    mode,
                    report_limit,
                    asset_id,
                ),
            )
            row = dict(cur.fetchone())
        conn.commit()
    return _serialize(row)


def set_cdp_port(crawl_id: UUID | str, port: int) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fnguide_crawls
                SET cdp_port = %s, pid = %s
                WHERE id = %s AND ended_at IS NULL
                RETURNING *
                """,
                (port, os.getpid(), str(crawl_id)),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"No open crawl {crawl_id}")
        conn.commit()
    return _serialize(dict(row))


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


def append_event(
    crawl_id: UUID | str,
    *,
    level: str,
    stage: str,
    event: str,
    detail: dict[str, Any] | None = None,
) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO fnguide_crawl_events (crawl_id, level, stage, event, detail)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                """,
                (
                    str(crawl_id),
                    level,
                    stage or "",
                    event,
                    json.dumps(detail or {}, ensure_ascii=False, default=str),
                ),
            )
        conn.commit()


def update_progress(crawl_id: UUID | str, fields: dict[str, Any]) -> dict[str, Any]:
    """Merge `fields` into crawls.progress (shallow)."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fnguide_crawls
                SET progress = COALESCE(progress, '{}'::jsonb) || %s::jsonb
                WHERE id = %s
                RETURNING *
                """,
                (
                    json.dumps(fields, ensure_ascii=False, default=str),
                    str(crawl_id),
                ),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"No crawl {crawl_id} for progress update")
        conn.commit()
    return _serialize(dict(row))


def list_events(crawl_id: UUID | str, *, limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, crawl_id, at, level, stage, event, detail
                FROM fnguide_crawl_events
                WHERE crawl_id = %s
                ORDER BY at DESC
                LIMIT %s
                """,
                (str(crawl_id), limit),
            )
            rows = cur.fetchall()
    return [_serialize_event(dict(r)) for r in rows]


def _serialize_event(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            out[key] = value.isoformat()
        elif isinstance(value, UUID):
            out[key] = str(value)
        else:
            out[key] = value
    detail = out.get("detail")
    if isinstance(detail, str):
        try:
            out["detail"] = json.loads(detail)
        except Exception:
            out["detail"] = {"raw": detail}
    elif detail is None:
        out["detail"] = {}
    return out


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            out[key] = value.isoformat()
        elif isinstance(value, UUID):
            out[key] = str(value)
        else:
            out[key] = value
    progress = out.get("progress")
    if isinstance(progress, str):
        try:
            out["progress"] = json.loads(progress)
        except Exception:
            out["progress"] = {}
    elif progress is None:
        out["progress"] = {}
    state = out.get("state")
    out["label"] = CRAWL_STATE_LABELS.get(str(state), "종료")
    out["terminal"] = str(state) in TERMINAL_STATES or out.get("ended_at") is not None
    port = out.get("cdp_port")
    out["cdp_http_url"] = f"http://127.0.0.1:{port}" if port else None
    return out
