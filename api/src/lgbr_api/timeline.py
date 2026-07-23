"""Session-grouped activity timeline for the monitor."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from lgbr_api.db import END_REASON_LABELS, STATE_LABELS, connect

SESSION_EVENT_LABELS = {
    "login_start": "로그인 시작",
    "login_ok": "로그인 완료",
    "login_fail": "로그인 실패",
    "touch": "세션 유지",
    "logout_request": "로그아웃 요청",
    "logout_ok": "로그아웃 완료",
    "external_logout": "외부 로그아웃",
    "error": "세션 오류",
}

KIND_LABELS = {
    "session": "로그인",
    "crawl": "크롤",
}


def _parse_detail(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except Exception:
            return {"raw": raw}
        return data if isinstance(data, dict) else {"raw": data}
    if raw is None:
        return {}
    return {"raw": raw}


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def _event_label(*, kind: str, event: str, stage: str | None) -> str:
    if kind == "session":
        return SESSION_EVENT_LABELS.get(event, event or "—")
    stage_s = (stage or "").strip() or "—"
    event_s = (event or "").strip() or "—"
    return f"{stage_s}/{event_s}"


def _serialize_event(row: dict[str, Any]) -> dict[str, Any]:
    kind = str(row.get("kind") or "")
    event = str(row.get("event") or "")
    stage = row.get("stage")
    stage_s = str(stage) if stage else None
    detail = _parse_detail(row.get("detail"))
    rid = row.get("id")
    ref = row.get("ref_id")
    return {
        "id": str(rid) if isinstance(rid, UUID) else str(rid),
        "at": _iso(row.get("at")),
        "kind": kind,
        "kind_label": KIND_LABELS.get(kind, kind),
        "event": event,
        "stage": stage_s,
        "level": row.get("level"),
        "label": _event_label(kind=kind, event=event, stage=stage_s),
        "detail": detail,
        "ref_id": str(ref) if ref is not None else None,
    }


def _serialize_session(row: dict[str, Any]) -> dict[str, Any]:
    sid = row["id"]
    state = str(row.get("state") or "")
    reason = row.get("end_reason")
    return {
        "id": str(sid) if isinstance(sid, UUID) else str(sid),
        "fnguide_user_id": row.get("fnguide_user_id"),
        "started_at": _iso(row.get("started_at")),
        "ended_at": _iso(row.get("ended_at")),
        "state": state,
        "label": STATE_LABELS.get(state, "로그아웃됨"),
        "end_reason_label": (
            END_REASON_LABELS.get(str(reason)) if reason else None
        ),
        "event_count": int(row.get("event_count") or 0),
        "crawl_count": int(row.get("crawl_count") or 0),
    }


def list_timeline(*, limit: int = 10, offset: int = 0) -> dict[str, Any]:
    """Paginated login sessions with event/crawl counts."""
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*)::int AS n FROM fnguide_sessions")
            total = int(cur.fetchone()["n"])
            cur.execute(
                """
                SELECT
                  s.id,
                  s.fnguide_user_id,
                  s.started_at,
                  s.ended_at,
                  s.state,
                  s.end_reason,
                  (
                    SELECT count(*)::int
                    FROM fnguide_session_events e
                    WHERE e.session_id = s.id
                  )
                  + (
                    SELECT count(*)::int
                    FROM fnguide_crawl_events ce
                    JOIN fnguide_crawls c ON c.id = ce.crawl_id
                    WHERE c.session_id = s.id
                  ) AS event_count,
                  (
                    SELECT count(*)::int
                    FROM fnguide_crawls c
                    WHERE c.session_id = s.id
                  ) AS crawl_count
                FROM fnguide_sessions s
                ORDER BY s.started_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            items = [_serialize_session(dict(r)) for r in cur.fetchall()]
    return {
        "ok": True,
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def list_session_timeline(
    session_id: str, *, limit: int = 50, offset: int = 0
) -> dict[str, Any]:
    """Events for one login session (session + linked crawl events)."""
    try:
        sid = str(UUID(session_id))
    except (TypeError, ValueError):
        return {
            "ok": False,
            "status": 400,
            "message": "invalid session id",
            "session_id": None,
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
        }

    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM fnguide_sessions WHERE id = %s",
                (sid,),
            )
            if cur.fetchone() is None:
                return {
                    "ok": False,
                    "status": 404,
                    "message": "session not found",
                    "session_id": sid,
                    "items": [],
                    "total": 0,
                    "limit": limit,
                    "offset": offset,
                }

            cur.execute(
                """
                SELECT
                  (
                    SELECT count(*)::int
                    FROM fnguide_session_events
                    WHERE session_id = %s
                  )
                  + (
                    SELECT count(*)::int
                    FROM fnguide_crawl_events ce
                    JOIN fnguide_crawls c ON c.id = ce.crawl_id
                    WHERE c.session_id = %s
                  ) AS n
                """,
                (sid, sid),
            )
            total = int(cur.fetchone()["n"])
            cur.execute(
                """
                SELECT * FROM (
                  SELECT
                    id,
                    at,
                    'session'::text AS kind,
                    event AS event,
                    NULL::text AS level,
                    NULL::text AS stage,
                    detail,
                    session_id::text AS ref_id
                  FROM fnguide_session_events
                  WHERE session_id = %s
                  UNION ALL
                  SELECT
                    ce.id,
                    ce.at,
                    'crawl'::text AS kind,
                    ce.event,
                    ce.level,
                    ce.stage,
                    ce.detail,
                    ce.crawl_id::text AS ref_id
                  FROM fnguide_crawl_events ce
                  JOIN fnguide_crawls c ON c.id = ce.crawl_id
                  WHERE c.session_id = %s
                ) t
                ORDER BY at DESC
                LIMIT %s OFFSET %s
                """,
                (sid, sid, limit, offset),
            )
            items = [_serialize_event(dict(r)) for r in cur.fetchall()]

    return {
        "ok": True,
        "session_id": sid,
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
