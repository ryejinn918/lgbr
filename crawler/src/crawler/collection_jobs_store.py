"""Persist source-agnostic collection jobs (feed / search / body fill)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from crawler.db import connect

JOB_STATE_LABELS = {
    "starting": "시작 중",
    "active": "수집 중",
    "stopping": "종료 중",
    "ended": "종료",
    "error": "오류",
}

VALID_CAPABILITIES = frozenset({"feed", "search", "fetch_body", "download"})
VALID_STATES = frozenset({"starting", "active", "stopping", "ended", "error"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_job(*, source: str, capability: str) -> dict[str, Any]:
    if capability not in VALID_CAPABILITIES:
        raise ValueError(f"invalid capability: {capability}")
    source_s = (source or "").strip()
    if not source_s:
        raise ValueError("source must not be empty")
    now = _now()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO collection_jobs
                    (source, capability, started_at, state)
                VALUES (%s, %s, %s, 'starting')
                RETURNING *
                """,
                (source_s, capability, now),
            )
            row = dict(cur.fetchone())
        conn.commit()
    return _serialize(row)


def claim_job(job_id: UUID | str) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE collection_jobs
                SET state = 'active',
                    pid = %s,
                    progress = COALESCE(progress, '{}'::jsonb)
                WHERE id = %s
                  AND ended_at IS NULL
                  AND state IN ('starting', 'active')
                RETURNING *
                """,
                (os.getpid(), str(job_id)),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"No open collection job {job_id}")
        conn.commit()
    return _serialize(dict(row))


def set_progress(job_id: UUID | str, progress: dict[str, Any]) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE collection_jobs
                SET progress = COALESCE(progress, '{}'::jsonb) || %s::jsonb
                WHERE id = %s AND ended_at IS NULL
                """,
                (json.dumps(progress, ensure_ascii=False), str(job_id)),
            )
        conn.commit()


def set_message(job_id: UUID | str, message: str | None) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE collection_jobs
                SET message = %s
                WHERE id = %s AND ended_at IS NULL
                """,
                (message, str(job_id)),
            )
        conn.commit()


def mark_stopping(job_id: UUID | str, *, message: str | None = None) -> None:
    now = _now()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE collection_jobs
                SET state = 'stopping',
                    stop_requested_at = COALESCE(stop_requested_at, %s),
                    message = COALESCE(%s, message)
                WHERE id = %s AND ended_at IS NULL
                """,
                (now, message, str(job_id)),
            )
        conn.commit()


def end_job(
    job_id: UUID | str,
    *,
    message: str | None = None,
    error: bool = False,
    progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _now()
    state = "error" if error else "ended"
    with connect() as conn:
        with conn.cursor() as cur:
            if progress is not None:
                cur.execute(
                    """
                    UPDATE collection_jobs
                    SET state = %s,
                        ended_at = %s,
                        message = COALESCE(%s, message),
                        progress = COALESCE(progress, '{}'::jsonb) || %s::jsonb
                    WHERE id = %s
                    RETURNING *
                    """,
                    (
                        state,
                        now,
                        message,
                        json.dumps(progress, ensure_ascii=False),
                        str(job_id),
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE collection_jobs
                    SET state = %s,
                        ended_at = %s,
                        message = COALESCE(%s, message)
                    WHERE id = %s
                    RETURNING *
                    """,
                    (state, now, message, str(job_id)),
                )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"Failed to end collection job {job_id}")
        conn.commit()
    return _serialize(dict(row))


def get_job(job_id: UUID | str) -> dict[str, Any] | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM collection_jobs WHERE id = %s",
                (str(job_id),),
            )
            row = cur.fetchone()
    return _serialize(dict(row)) if row else None


def get_open_job(
    *, source: str | None = None, capability: str | None = None
) -> dict[str, Any] | None:
    where = ["ended_at IS NULL"]
    params: list[Any] = []
    if source:
        where.append("source = %s")
        params.append(source)
    if capability:
        where.append("capability = %s")
        params.append(capability)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM collection_jobs
                WHERE {" AND ".join(where)}
                ORDER BY started_at DESC
                LIMIT 1
                """,
                params,
            )
            row = cur.fetchone()
    return _serialize(dict(row)) if row else None


def get_latest_job(
    *, source: str | None = None, capability: str | None = None
) -> dict[str, Any] | None:
    where: list[str] = []
    params: list[Any] = []
    if source:
        where.append("source = %s")
        params.append(source)
    if capability:
        where.append("capability = %s")
        params.append(capability)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM collection_jobs
                {where_sql}
                ORDER BY started_at DESC
                LIMIT 1
                """,
                params,
            )
            row = cur.fetchone()
    return _serialize(dict(row)) if row else None


def request_stop(
    *, source: str | None = None, capability: str | None = None
) -> dict[str, Any] | None:
    now = _now()
    where = ["ended_at IS NULL"]
    params: list[Any] = []
    if source:
        where.append("source = %s")
        params.append(source)
    if capability:
        where.append("capability = %s")
        params.append(capability)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE collection_jobs
                SET stop_requested_at = COALESCE(stop_requested_at, %s)
                WHERE id = (
                    SELECT id FROM collection_jobs
                    WHERE {" AND ".join(where)}
                    ORDER BY started_at DESC
                    LIMIT 1
                )
                RETURNING *
                """,
                [now, *params],
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize(dict(row)) if row else None


def stop_requested(job_id: UUID | str) -> bool:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT stop_requested_at, ended_at, state
                FROM collection_jobs
                WHERE id = %s
                """,
                (str(job_id),),
            )
            row = cur.fetchone()
    if not row:
        return True
    if row.get("ended_at") or row.get("state") in ("ended", "error"):
        return True
    return bool(row.get("stop_requested_at"))


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
    out["label"] = JOB_STATE_LABELS.get(str(state), "종료")
    return out
