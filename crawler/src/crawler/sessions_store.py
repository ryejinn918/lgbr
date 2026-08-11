"""Persist Fnguide account sessions and events in Postgres."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from crawler.db import END_REASON_LABELS, STATE_LABELS, connect


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_session(
    *,
    source: str,
    fnguide_user_id: str,
    ttl_seconds: int,
) -> dict[str, Any]:
    now = _now()
    lease_until = now + timedelta(seconds=ttl_seconds)
    source_s = (source or "").strip().lower() or "fnguide"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO fnguide_sessions (
                    source, fnguide_user_id, started_at, last_used_at, lease_until,
                    pid, state
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'logging_in')
                RETURNING *
                """,
                (source_s, fnguide_user_id, now, now, lease_until, os.getpid()),
            )
            row = dict(cur.fetchone())
            _add_event(cur, row["id"], "login_start", {"pid": os.getpid()})
        conn.commit()
    return _serialize(row)


def mark_logged_in(
    session_id: UUID | str,
    *,
    current_url: str | None = None,
    step: str | None = None,
) -> dict[str, Any]:
    now = _now()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fnguide_sessions
                SET state = 'logged_in',
                    last_used_at = %s,
                    current_url = %s,
                    step = %s,
                    message = NULL,
                    pid = %s
                WHERE id = %s
                RETURNING *
                """,
                (now, current_url, step, os.getpid(), str(session_id)),
            )
            row = dict(cur.fetchone())
            _add_event(cur, row["id"], "login_ok", {"current_url": current_url})
        conn.commit()
    return _serialize(row)


def mark_login_failed(session_id: UUID | str, message: str) -> dict[str, Any]:
    now = _now()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fnguide_sessions
                SET state = 'error',
                    ended_at = %s,
                    end_reason = 'error',
                    message = %s
                WHERE id = %s
                RETURNING *
                """,
                (now, message, str(session_id)),
            )
            row = dict(cur.fetchone())
            _add_event(cur, row["id"], "login_fail", {"message": message})
        conn.commit()
    return _serialize(row)


def touch(
    session_id: UUID | str,
    *,
    current_url: str | None = None,
    step: str | None = None,
) -> dict[str, Any]:
    now = _now()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fnguide_sessions
                SET last_used_at = %s,
                    current_url = COALESCE(%s, current_url),
                    step = COALESCE(%s, step),
                    pid = %s
                WHERE id = %s AND ended_at IS NULL
                RETURNING *
                """,
                (now, current_url, step, os.getpid(), str(session_id)),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"No open session {session_id}")
            row = dict(row)
            _add_event(
                cur,
                row["id"],
                "touch",
                {"current_url": current_url, "step": step},
            )
        conn.commit()
    return _serialize(row)


def begin_logout(session_id: UUID | str) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fnguide_sessions
                SET state = 'logging_out', pid = %s
                WHERE id = %s AND ended_at IS NULL
                RETURNING *
                """,
                (os.getpid(), str(session_id)),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"No open session {session_id}")
            row = dict(row)
        conn.commit()
    return _serialize(row)


def end_session(
    session_id: UUID | str,
    *,
    end_reason: str,
    message: str | None = None,
    event: str | None = None,
) -> dict[str, Any]:
    now = _now()
    event_name = event or (
        "external_logout" if end_reason == "external" else "logout_ok"
    )
    if end_reason == "error":
        event_name = "error"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fnguide_sessions
                SET state = CASE WHEN %s = 'error' THEN 'error' ELSE 'ended' END,
                    ended_at = %s,
                    end_reason = %s,
                    message = %s,
                    logout_requested_at = COALESCE(logout_requested_at, %s)
                WHERE id = %s
                RETURNING *
                """,
                (
                    end_reason,
                    now,
                    end_reason,
                    message,
                    now if end_reason == "manual" else None,
                    str(session_id),
                ),
            )
            row = dict(cur.fetchone())
            _add_event(
                cur,
                row["id"],
                event_name,
                {"end_reason": end_reason, "message": message},
            )
        conn.commit()
    return _serialize(row)


def get_open_session(source: str | None = None) -> dict[str, Any] | None:
    source_s = (source or "").strip().lower() or None
    with connect() as conn:
        with conn.cursor() as cur:
            if source_s:
                cur.execute(
                    """
                    SELECT *
                    FROM fnguide_sessions
                    WHERE ended_at IS NULL AND source = %s
                    ORDER BY started_at DESC
                    LIMIT 1
                    """,
                    (source_s,),
                )
            else:
                cur.execute(
                    """
                    SELECT *
                    FROM fnguide_sessions
                    WHERE ended_at IS NULL
                    ORDER BY started_at DESC
                    LIMIT 1
                    """
                )
            row = cur.fetchone()
    return _serialize(dict(row)) if row else None


def get_session(session_id: UUID | str) -> dict[str, Any] | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM fnguide_sessions WHERE id = %s",
                (str(session_id),),
            )
            row = cur.fetchone()
    return _serialize(dict(row)) if row else None


def request_logout(source: str | None = None) -> dict[str, Any] | None:
    now = _now()
    source_s = (source or "").strip().lower() or None
    with connect() as conn:
        with conn.cursor() as cur:
            if source_s:
                cur.execute(
                    """
                    UPDATE fnguide_sessions
                    SET logout_requested_at = %s
                    WHERE id = (
                        SELECT id FROM fnguide_sessions
                        WHERE ended_at IS NULL AND source = %s
                        ORDER BY started_at DESC
                        LIMIT 1
                    )
                    AND logout_requested_at IS NULL
                    RETURNING *
                    """,
                    (now, source_s),
                )
            else:
                cur.execute(
                    """
                    UPDATE fnguide_sessions
                    SET logout_requested_at = %s
                    WHERE id = (
                        SELECT id FROM fnguide_sessions
                        WHERE ended_at IS NULL
                        ORDER BY started_at DESC
                        LIMIT 1
                    )
                    AND logout_requested_at IS NULL
                    RETURNING *
                    """,
                    (now,),
                )
            row = cur.fetchone()
            if not row:
                if source_s:
                    cur.execute(
                        """
                        SELECT * FROM fnguide_sessions
                        WHERE ended_at IS NULL AND source = %s
                        ORDER BY started_at DESC
                        LIMIT 1
                        """,
                        (source_s,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM fnguide_sessions
                        WHERE ended_at IS NULL
                        ORDER BY started_at DESC
                        LIMIT 1
                        """
                    )
                existing = cur.fetchone()
                conn.commit()
                return _serialize(dict(existing)) if existing else None
            row = dict(row)
            _add_event(cur, row["id"], "logout_request", {})
        conn.commit()
    return _serialize(row)


def list_history(*, limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM fnguide_sessions
                ORDER BY started_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
    return [_serialize(dict(r)) for r in rows]


def _add_event(cur: Any, session_id: Any, event: str, detail: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO fnguide_session_events (session_id, event, detail)
        VALUES (%s, %s, %s::jsonb)
        """,
        (str(session_id), event, json.dumps(detail, ensure_ascii=False)),
    )


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
    out["label"] = STATE_LABELS.get(str(state), "로그아웃됨")
    reason = out.get("end_reason")
    out["end_reason_label"] = (
        END_REASON_LABELS.get(str(reason)) if reason else None
    )
    return out
