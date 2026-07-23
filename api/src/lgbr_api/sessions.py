"""Read/update Fnguide sessions for the monitor API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from lgbr_api.db import END_REASON_LABELS, STATE_LABELS, connect


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_current_session() -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
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
    if not row:
        return {
            "state": "ended",
            "label": "로그아웃됨",
            "session": None,
        }
    session = _serialize(dict(row))
    return {
        "state": session["state"],
        "label": session["label"],
        "session": session,
    }


def request_logout() -> dict[str, Any]:
    now = _now()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM fnguide_sessions
                WHERE ended_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
            existing = cur.fetchone()
            if not existing:
                conn.commit()
                return {
                    "ok": False,
                    "label": "로그아웃됨",
                    "message": "사용 중인 계정이 없습니다.",
                    "session": None,
                }
            existing = dict(existing)
            if existing.get("logout_requested_at") is not None:
                session = _serialize(existing)
                conn.commit()
                return {
                    "ok": True,
                    "label": session["label"],
                    "message": "이미 로그아웃이 요청되었습니다.",
                    "session": session,
                }
            cur.execute(
                """
                UPDATE fnguide_sessions
                SET logout_requested_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (now, existing["id"]),
            )
            row = dict(cur.fetchone())
            cur.execute(
                """
                INSERT INTO fnguide_session_events (session_id, event, detail)
                VALUES (%s, 'logout_request', '{}'::jsonb)
                """,
                (row["id"],),
            )
        conn.commit()
    session = _serialize(row)
    return {
        "ok": True,
        "label": session["label"],
        "message": "로그아웃을 요청했습니다.",
        "session": session,
    }


def list_history(
    *, limit: int = 50, offset: int = 0
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*)::int AS n FROM fnguide_sessions")
            total = int(cur.fetchone()["n"])
            cur.execute(
                """
                SELECT *
                FROM fnguide_sessions
                ORDER BY started_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            rows = cur.fetchall()
    return {
        "items": [_serialize(dict(r)) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


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
