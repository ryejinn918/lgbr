"""Crawl status and manual start for the monitor API.

Fail-closed rules:
- At most one open crawl / open session.
- Dead worker pid → open crawl forced to error.
- Start rejected if open crawl or orphan open session remains.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from lgbr_api.db import CRAWL_STATE_LABELS, connect
from lgbr_api.sessions import get_current_session, request_logout

ROOT = Path(__file__).resolve().parents[3]
CRAWL_LOG = ROOT / ".crawler" / "crawl.log"


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


def reconcile_stale_crawls() -> list[dict[str, Any]]:
    """Mark open crawls with dead pid as error. Returns affected rows."""
    now = _now()
    fixed: list[dict[str, Any]] = []
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM fnguide_crawls
                WHERE ended_at IS NULL
                ORDER BY started_at ASC
                """
            )
            rows = [dict(r) for r in cur.fetchall()]
            for row in rows:
                pid = row.get("pid")
                # starting without pid yet: give API spawn a short grace via started_at?
                # If pid is null and starting for > 60s, treat as failed spawn.
                if pid is None:
                    started = row.get("started_at")
                    if isinstance(started, datetime):
                        age = (now - started.astimezone(timezone.utc)).total_seconds()
                    else:
                        age = 9999
                    if row.get("state") == "starting" and age < 60:
                        continue
                    message = "crawl worker never claimed pid"
                elif _pid_alive(int(pid)):
                    continue
                else:
                    message = f"crawl worker pid {pid} is dead"
                cur.execute(
                    """
                    UPDATE fnguide_crawls
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
            # Orphan open sessions with no open crawl → error-close them.
            cur.execute(
                """
                SELECT s.*
                FROM fnguide_sessions s
                WHERE s.ended_at IS NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM fnguide_crawls c
                    WHERE c.ended_at IS NULL AND c.session_id = s.id
                  )
                """
            )
            orphans = [dict(r) for r in cur.fetchall()]
            for sess in orphans:
                spid = sess.get("pid")
                # Live worker without crawl row: leave open so start stays blocked.
                if spid is not None and _pid_alive(int(spid)):
                    continue
                cur.execute(
                    """
                    UPDATE fnguide_sessions
                    SET state = 'error',
                        ended_at = %s,
                        end_reason = 'error',
                        message = COALESCE(message, %s)
                    WHERE id = %s AND ended_at IS NULL
                    RETURNING id
                    """,
                    (now, "orphan session without open crawl", sess["id"]),
                )
        conn.commit()
    return fixed


def get_current_crawl() -> dict[str, Any]:
    reconcile_stale_crawls()
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
            if row:
                crawl = _serialize(dict(row))
                return {
                    "state": crawl["state"],
                    "label": crawl["label"],
                    "crawl": crawl,
                    "session": get_current_session(),
                    "can_start": False,
                }
            cur.execute(
                """
                SELECT *
                FROM fnguide_crawls
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
            last = cur.fetchone()
    account = get_current_session()
    can_start = account.get("session") is None
    if not last:
        return {
            "state": "ended",
            "label": "종료",
            "crawl": None,
            "session": account,
            "can_start": can_start,
        }
    crawl = _serialize(dict(last))
    # No open crawl → idle is always 종료. Last error stays on the row only.
    return {
        "state": "ended",
        "label": "종료",
        "crawl": crawl,
        "session": account,
        "can_start": can_start,
    }


def request_stop() -> dict[str, Any]:
    """Ask crawl to stop and request account logout (subtask)."""
    reconcile_stale_crawls()
    now = _now()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fnguide_crawls
                SET stop_requested_at = COALESCE(stop_requested_at, %s)
                WHERE id = (
                    SELECT id FROM fnguide_crawls
                    WHERE ended_at IS NULL
                    ORDER BY started_at DESC
                    LIMIT 1
                )
                RETURNING *
                """,
                (now,),
            )
            crawl_row = cur.fetchone()
        conn.commit()

    logout = request_logout()
    account = get_current_session()
    if not crawl_row:
        return {
            "ok": bool(logout.get("ok")),
            "label": "종료",
            "message": logout.get("message", "실행 중인 크롤이 없습니다."),
            "crawl": None,
            "session": account,
            "can_start": account.get("session") is None,
        }
    crawl = _serialize(dict(crawl_row))
    return {
        "ok": True,
        "label": crawl["label"],
        "message": "종료를 요청했습니다.",
        "crawl": crawl,
        "session": account,
        "can_start": False,
    }


def start_crawl() -> dict[str, Any]:
    reconcile_stale_crawls()
    open_crawl = _get_open_row()
    if open_crawl:
        crawl = _serialize(open_crawl)
        return {
            "ok": False,
            "status": 409,
            "label": crawl["label"],
            "message": "이미 크롤이 실행 중입니다.",
            "crawl": crawl,
            "session": get_current_session(),
            "can_start": False,
        }

    account = get_current_session()
    if account.get("session") is not None:
        return {
            "ok": False,
            "status": 409,
            "label": "오류",
            "message": "열린 계정 세션이 남아 있어 시작할 수 없습니다.",
            "crawl": None,
            "session": account,
            "can_start": False,
        }

    try:
        crawl = _create_starting_crawl()
    except Exception as exc:
        return {
            "ok": False,
            "status": 500,
            "label": "오류",
            "message": f"크롤 행 생성 실패: {exc}",
            "crawl": None,
            "session": get_current_session(),
            "can_start": False,
        }

    python = ROOT / ".venv" / "bin" / "python"
    if not python.is_file():
        python = Path(sys.executable)

    CRAWL_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(CRAWL_LOG, "a", encoding="utf-8")  # noqa: SIM115
    try:
        log_f.write(f"\n--- crawl start {_now().isoformat()} id={crawl['id']} ---\n")
        log_f.flush()
        subprocess.Popen(
            [
                str(python),
                "-m",
                "crawler",
                "crawl",
                "run",
                "--headless",
                "--crawl-id",
                crawl["id"],
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
            _fail_crawl(crawl["id"], message=str(exc))
        except Exception as db_exc:
            return {
                "ok": False,
                "status": 500,
                "label": "오류",
                "message": f"크롤 시작 실패: {exc}; DB error mark failed: {db_exc}",
                "crawl": crawl,
                "session": get_current_session(),
                "can_start": False,
            }
        return {
            "ok": False,
            "status": 500,
            "label": "오류",
            "message": f"크롤 시작 실패: {exc}",
            "crawl": None,
            "session": get_current_session(),
            "can_start": get_current_session().get("session") is None,
        }

    return {
        "ok": True,
        "status": 202,
        "label": crawl["label"],
        "message": "크롤을 시작했습니다.",
        "crawl": crawl,
        "session": get_current_session(),
        "can_start": False,
    }


def _create_starting_crawl() -> dict[str, Any]:
    now = _now()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO fnguide_crawls (started_at, state)
                VALUES (%s, 'starting')
                RETURNING *
                """,
                (now,),
            )
            row = dict(cur.fetchone())
        conn.commit()
    return _serialize(row)


def _fail_crawl(crawl_id: str, *, message: str | None = None) -> None:
    now = _now()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fnguide_crawls
                SET state = 'error', ended_at = %s, message = %s
                WHERE id = %s
                """,
                (now, message, crawl_id),
            )
            if cur.rowcount != 1:
                raise RuntimeError(f"Failed to mark crawl {crawl_id} as error")
        conn.commit()


def _get_open_row() -> dict[str, Any] | None:
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
    state = out.get("state")
    out["label"] = CRAWL_STATE_LABELS.get(str(state), "종료")
    return out
