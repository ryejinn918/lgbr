"""Source-agnostic collection jobs (list expansion / body fill).

Separate from fnguide_crawls. Feed + ARG fetch_body.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from lgbr_api.db import connect

ROOT = Path(__file__).resolve().parents[3]
FEED_LOG = ROOT / ".crawler" / "feed.log"
FETCH_BODY_LOG = ROOT / ".crawler" / "fetch_body.log"

JOB_STATE_LABELS = {
    "starting": "시작 중",
    "active": "수집 중",
    "stopping": "종료 중",
    "ended": "종료",
    "error": "오류",
}

FEED_ALLOWLIST = frozenset({"arg"})
VALID_CAPABILITIES = frozenset({"feed", "search", "fetch_body", "download"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pid_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def reconcile_stale_jobs() -> list[dict[str, Any]]:
    now = _now()
    fixed: list[dict[str, Any]] = []
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM collection_jobs
                WHERE ended_at IS NULL
                ORDER BY started_at ASC
                """
            )
            rows = [dict(r) for r in cur.fetchall()]
            for row in rows:
                pid = row.get("pid")
                if pid is None:
                    started = row.get("started_at")
                    if isinstance(started, datetime):
                        age = (
                            now - started.astimezone(timezone.utc)
                        ).total_seconds()
                    else:
                        age = 9999
                    if row.get("state") == "starting" and age < 60:
                        continue
                    message = "collection worker never claimed pid"
                elif _pid_alive(int(pid)):
                    continue
                else:
                    message = f"collection worker pid {pid} is dead"
                cur.execute(
                    """
                    UPDATE collection_jobs
                    SET state = 'error',
                        ended_at = %s,
                        message = COALESCE(message, %s)
                    WHERE id = %s AND ended_at IS NULL
                    RETURNING *
                    """,
                    (now, message, row["id"]),
                )
                updated = cur.fetchone()
                if updated:
                    fixed.append(_serialize(dict(updated)))
        conn.commit()
    return fixed


def get_current_job(
    *,
    source: str | None = None,
    capability: str | None = "feed",
) -> dict[str, Any]:
    reconcile_stale_jobs()
    open_job = _get_open(source=source, capability=capability)
    if open_job:
        job = _serialize(open_job)
        return {
            "state": job["state"],
            "label": job["label"],
            "job": job,
            "progress": job.get("progress") or {},
            "can_start": False,
        }
    last = _get_latest(source=source, capability=capability)
    if last:
        job = _serialize(last)
        return {
            "state": job["state"],
            "label": job["label"],
            "job": job,
            "progress": job.get("progress") or {},
            "can_start": job["state"] != "error",
        }
    return {
        "state": "ended",
        "label": "종료",
        "job": None,
        "progress": {},
        "can_start": True,
    }


DEFAULT_PERIOD_MONTHS = 3
MIN_PERIOD_MONTHS = 1
MAX_PERIOD_MONTHS = 24


def start_feed(
    *,
    source: str = "arg",
    max_pages: int | None = None,
    period_months: int | None = None,
) -> dict[str, Any]:
    source_s = (source or "").strip().lower()
    if source_s not in FEED_ALLOWLIST:
        return {
            "ok": False,
            "status": 400,
            "label": "오류",
            "message": f"source must be one of: {', '.join(sorted(FEED_ALLOWLIST))}",
            "job": None,
            "can_start": False,
        }

    pages = 50 if max_pages is None else int(max_pages)
    if pages < 1 or pages > 200:
        return {
            "ok": False,
            "status": 400,
            "label": "오류",
            "message": "max_pages must be between 1 and 200",
            "job": None,
            "can_start": False,
        }

    months = (
        DEFAULT_PERIOD_MONTHS if period_months is None else int(period_months)
    )
    if months < MIN_PERIOD_MONTHS or months > MAX_PERIOD_MONTHS:
        return {
            "ok": False,
            "status": 400,
            "label": "오류",
            "message": (
                f"period_months must be between "
                f"{MIN_PERIOD_MONTHS} and {MAX_PERIOD_MONTHS}"
            ),
            "job": None,
            "can_start": False,
        }

    reconcile_stale_jobs()
    open_job = _get_open(source=source_s, capability="feed")
    if open_job:
        job = _serialize(open_job)
        return {
            "ok": False,
            "status": 409,
            "label": job["label"],
            "message": "이미 해당 소스 feed 잡이 실행 중입니다.",
            "job": job,
            "can_start": False,
        }

    try:
        job = _create_job(source=source_s, capability="feed")
    except Exception as exc:
        return {
            "ok": False,
            "status": 500,
            "label": "오류",
            "message": f"잡 행 생성 실패: {exc}",
            "job": None,
            "can_start": False,
        }

    python = ROOT / ".venv" / "bin" / "python"
    if not python.is_file():
        python = Path(sys.executable)

    FEED_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(FEED_LOG, "a", encoding="utf-8")  # noqa: SIM115
    try:
        log_f.write(
            f"\n--- feed start {_now().isoformat()} "
            f"id={job['id']} source={source_s} "
            f"period_months={months} max_pages={pages} ---\n"
        )
        log_f.flush()
        subprocess.Popen(
            [
                str(python),
                "-m",
                "crawler",
                "feed",
                "run",
                "--job-id",
                job["id"],
                "--max-pages",
                str(pages),
                "--period-months",
                str(months),
            ],
            cwd=str(ROOT),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=os.environ.copy(),
        )
    except Exception as exc:
        log_f.close()
        try:
            _fail_job(job["id"], message=str(exc))
        except Exception as db_exc:
            return {
                "ok": False,
                "status": 500,
                "label": "오류",
                "message": f"feed 시작 실패: {exc}; DB mark failed: {db_exc}",
                "job": job,
                "can_start": False,
            }
        return {
            "ok": False,
            "status": 500,
            "label": "오류",
            "message": f"feed 시작 실패: {exc}",
            "job": None,
            "can_start": False,
        }

    return {
        "ok": True,
        "status": 202,
        "state": job["state"],
        "label": job["label"],
        "message": f"{source_s} feed 목록 확장을 시작했습니다.",
        "job": job,
        "progress": job.get("progress") or {},
        "can_start": False,
    }


DEFAULT_BODY_LIMIT = 200
MIN_BODY_LIMIT = 1
MAX_BODY_LIMIT = 1000
DEFAULT_DELAY_SECONDS = 1.0
MIN_DELAY_SECONDS = 0.5
MAX_DELAY_SECONDS = 5.0
BODY_ALLOWLIST = frozenset({"arg"})


def start_fetch_body(
    *,
    source: str = "arg",
    limit: int | None = None,
    delay_seconds: float | None = None,
) -> dict[str, Any]:
    source_s = (source or "").strip().lower()
    if source_s not in BODY_ALLOWLIST:
        return {
            "ok": False,
            "status": 400,
            "label": "오류",
            "message": (
                "source must be one of: "
                + ", ".join(sorted(BODY_ALLOWLIST))
            ),
            "job": None,
            "can_start": False,
        }

    lim = DEFAULT_BODY_LIMIT if limit is None else int(limit)
    if lim < MIN_BODY_LIMIT or lim > MAX_BODY_LIMIT:
        return {
            "ok": False,
            "status": 400,
            "label": "오류",
            "message": (
                f"limit must be between {MIN_BODY_LIMIT} and {MAX_BODY_LIMIT}"
            ),
            "job": None,
            "can_start": False,
        }

    delay = (
        DEFAULT_DELAY_SECONDS
        if delay_seconds is None
        else float(delay_seconds)
    )
    if delay < MIN_DELAY_SECONDS or delay > MAX_DELAY_SECONDS:
        return {
            "ok": False,
            "status": 400,
            "label": "오류",
            "message": (
                f"delay_seconds must be between "
                f"{MIN_DELAY_SECONDS} and {MAX_DELAY_SECONDS}"
            ),
            "job": None,
            "can_start": False,
        }

    reconcile_stale_jobs()
    open_job = _get_open(source=source_s, capability="fetch_body")
    if open_job:
        job = _serialize(open_job)
        return {
            "ok": False,
            "status": 409,
            "label": job["label"],
            "message": "이미 해당 소스 본문 채우기 잡이 실행 중입니다.",
            "job": job,
            "can_start": False,
        }

    try:
        job = _create_job(source=source_s, capability="fetch_body")
    except Exception as exc:
        return {
            "ok": False,
            "status": 500,
            "label": "오류",
            "message": f"잡 행 생성 실패: {exc}",
            "job": None,
            "can_start": False,
        }

    python = ROOT / ".venv" / "bin" / "python"
    if not python.is_file():
        python = Path(sys.executable)

    FETCH_BODY_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(FETCH_BODY_LOG, "a", encoding="utf-8")  # noqa: SIM115
    try:
        log_f.write(
            f"\n--- fetch_body start {_now().isoformat()} "
            f"id={job['id']} source={source_s} "
            f"limit={lim} delay={delay} ---\n"
        )
        log_f.flush()
        subprocess.Popen(
            [
                str(python),
                "-m",
                "crawler",
                "fetch-body",
                "run",
                "--job-id",
                job["id"],
                "--limit",
                str(lim),
                "--delay",
                str(delay),
            ],
            cwd=str(ROOT),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=os.environ.copy(),
        )
    except Exception as exc:
        log_f.close()
        try:
            _fail_job(job["id"], message=str(exc))
        except Exception as db_exc:
            return {
                "ok": False,
                "status": 500,
                "label": "오류",
                "message": (
                    f"fetch_body 시작 실패: {exc}; DB mark failed: {db_exc}"
                ),
                "job": job,
                "can_start": False,
            }
        return {
            "ok": False,
            "status": 500,
            "label": "오류",
            "message": f"fetch_body 시작 실패: {exc}",
            "job": None,
            "can_start": False,
        }

    return {
        "ok": True,
        "status": 202,
        "state": job["state"],
        "label": job["label"],
        "message": f"{source_s} 본문 채우기를 시작했습니다.",
        "job": job,
        "progress": job.get("progress") or {},
        "can_start": False,
    }


def request_stop(
    *,
    source: str | None = None,
    capability: str | None = "feed",
) -> dict[str, Any]:
    reconcile_stale_jobs()
    now = _now()
    where = ["ended_at IS NULL"]
    params: list[Any] = [now]
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
                SET stop_requested_at = COALESCE(stop_requested_at, %s),
                    state = CASE
                        WHEN state IN ('starting', 'active') THEN 'stopping'
                        ELSE state
                    END,
                    message = COALESCE(message, 'stop requested')
                WHERE id = (
                    SELECT id FROM collection_jobs
                    WHERE {" AND ".join(where)}
                    ORDER BY started_at DESC
                    LIMIT 1
                )
                RETURNING *
                """,
                params,
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return {
            "ok": False,
            "label": "종료",
            "message": "실행 중인 잡이 없습니다.",
            "job": None,
            "can_start": True,
        }
    job = _serialize(dict(row))
    return {
        "ok": True,
        "label": job["label"],
        "message": "중단을 요청했습니다.",
        "job": job,
        "can_start": False,
    }


def _create_job(*, source: str, capability: str) -> dict[str, Any]:
    if capability not in VALID_CAPABILITIES:
        raise ValueError(f"invalid capability: {capability}")
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
                (source, capability, now),
            )
            row = dict(cur.fetchone())
        conn.commit()
    return _serialize(row)


def _fail_job(job_id: UUID | str, *, message: str) -> None:
    now = _now()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE collection_jobs
                SET state = 'error',
                    ended_at = %s,
                    message = %s
                WHERE id = %s AND ended_at IS NULL
                """,
                (now, message, str(job_id)),
            )
        conn.commit()


def _get_open(
    *, source: str | None, capability: str | None
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
    return dict(row) if row else None


def _get_latest(
    *, source: str | None, capability: str | None
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
    return dict(row) if row else None


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
