"""Crawl status and manual start for the monitor API.

Fail-closed rules:
- At most one open crawl / open session.
- Dead worker pid → open crawl forced to error.
- Start rejected if open crawl or orphan open session remains.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from uuid import UUID

from lgbr_api.asset_id import make_asset_id
from lgbr_api.db import CRAWL_STATE_LABELS, connect, database_url
from lgbr_api.sessions import get_current_session, request_logout
from lgbr_api.source_registry import (
    cdp_modes,
    no_account_modes,
    valid_crawl_modes,
)

ROOT = Path(__file__).resolve().parents[3]
CRAWL_LOG = ROOT / ".crawler" / "crawl.log"
DEFAULT_EVENT_LIMIT = 50


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


def list_crawl_events(
    crawl_id: str | None = None, *, limit: int = DEFAULT_EVENT_LIMIT
) -> dict[str, Any]:
    """List recent events for a crawl (default: newest crawl)."""
    limit = max(1, min(int(limit), 500))
    with connect() as conn:
        with conn.cursor() as cur:
            if crawl_id is None:
                cur.execute(
                    """
                    SELECT id FROM fnguide_crawls
                    ORDER BY started_at DESC
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
                if not row:
                    return {"crawl_id": None, "items": []}
                crawl_id = str(row["id"])
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
            items = [_serialize_event(dict(r)) for r in cur.fetchall()]
    return {"crawl_id": str(crawl_id), "items": items}


def get_current_crawl(*, event_limit: int = DEFAULT_EVENT_LIMIT) -> dict[str, Any]:
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
                events = list_crawl_events(crawl["id"], limit=event_limit)["items"]
                return {
                    "state": crawl["state"],
                    "label": crawl["label"],
                    "crawl": crawl,
                    "progress": crawl.get("progress") or {},
                    "events": events,
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
    if not last:
        return {
            "state": "ended",
            "label": "종료",
            "crawl": None,
            "progress": {},
            "events": [],
            "session": account,
            "can_start": account.get("session") is None,
        }
    crawl = _serialize(dict(last))
    events = list_crawl_events(crawl["id"], limit=event_limit)["items"]
    # Latest error blocks casual restart until fnguide_crawls.state is cleared.
    if crawl.get("state") == "error":
        return {
            "state": "error",
            "label": "오류",
            "crawl": crawl,
            "progress": crawl.get("progress") or {},
            "events": events,
            "session": account,
            "can_start": False,
            **_unblock_directions(crawl["id"]),
        }
    return {
        "state": "ended",
        "label": "종료",
        "crawl": crawl,
        "progress": crawl.get("progress") or {},
        "events": events,
        "session": account,
        "can_start": account.get("session") is None,
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


def shutdown_open_crawl(*, timeout_seconds: float = 60.0) -> dict[str, Any]:
    """Request stop on any open crawl and wait until it ends (API process exit)."""
    open_before = _get_open_row()
    if open_before is None:
        return {"ok": True, "stopped": False, "timed_out": False}

    request_stop()
    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    while time.monotonic() < deadline:
        if _get_open_row() is None:
            return {
                "ok": True,
                "stopped": True,
                "timed_out": False,
                "crawl_id": str(open_before.get("id")),
            }
        time.sleep(0.5)

    still_open = _get_open_row()
    return {
        "ok": still_open is None,
        "stopped": still_open is None,
        "timed_out": still_open is not None,
        "crawl_id": str(open_before.get("id")),
    }


VALID_MODES = valid_crawl_modes()
NO_ACCOUNT_MODES = no_account_modes()
CDP_STATUS_MODES = cdp_modes()
LIMITED_MODES = frozenset(
    {
        "ai",
        "physical_ai",
        "appliance",
        "display",
        "automotive",
        "petrochemical",
    }
)
DEFAULT_PERIOD_MONTHS = 3


def start_crawl(
    *,
    mode: str = "auto",
    limit: int | None = None,
    debug: bool = False,
    catalog: str | None = None,
) -> dict[str, Any]:
    # `limit` kept for API compat; search crawls use profile period_months.
    _ = limit
    # Legacy: datacenter crawl merged into ai (AI/AIDC).
    if mode == "datacenter":
        mode = "ai"
    if mode not in VALID_MODES:
        return {
            "ok": False,
            "status": 400,
            "label": "오류",
            "message": (
                "mode must be one of: "
                + ", ".join(sorted(VALID_MODES))
            ),
            "crawl": None,
            "session": get_current_session(),
            "can_start": False,
        }

    period_months: int | None = None
    use_debug = bool(debug) and mode in LIMITED_MODES
    if mode in LIMITED_MODES:
        from lgbr_api.profiles import get_profile

        prof = get_profile(mode)
        if prof.get("ok") and prof.get("profile"):
            try:
                period_months = int(prof["profile"].get("period_months") or DEFAULT_PERIOD_MONTHS)
            except (TypeError, ValueError):
                period_months = DEFAULT_PERIOD_MONTHS
        else:
            period_months = DEFAULT_PERIOD_MONTHS
        if period_months not in (3, 6, 12):
            period_months = DEFAULT_PERIOD_MONTHS

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

    blocking = _get_latest_error()
    if blocking:
        crawl = _serialize(blocking)
        directions = _unblock_directions(crawl["id"])
        return {
            "ok": False,
            "status": 409,
            "label": "오류",
            "message": (
                "이전 크롤이 error 상태라 재실행할 수 없습니다. "
                "점검 후 DB에 접속해 fnguide_crawls.state 를 ended 로 바꾸세요."
            ),
            "crawl": crawl,
            "session": get_current_session(),
            "can_start": False,
            **directions,
        }

    # PwC / Accenture adhoc do not use fnguide_sessions.
    if mode not in NO_ACCOUNT_MODES:
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

    pwc_catalog = "kr"
    if mode == "pwc":
        pwc_catalog = (catalog or "kr").strip().lower() or "kr"
        if pwc_catalog not in ("kr", "gx"):
            return {
                "ok": False,
                "status": 400,
                "label": "오류",
                "message": "catalog must be kr or gx for mode=pwc",
                "crawl": None,
                "session": get_current_session(),
                "can_start": False,
            }

    try:
        crawl = _create_starting_crawl(
            mode=mode, period_months=period_months, debug=use_debug
            )
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
    child_env = os.environ.copy()
    if mode == "pwc":
        child_env["PWC_CATALOG"] = pwc_catalog
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
            env=child_env,
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
            "can_start": False,
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


def _create_starting_crawl(
    *,
    mode: str = "auto",
    period_months: int | None = None,
    debug: bool = False,
) -> dict[str, Any]:
    now = _now()
    asset_id = make_asset_id(
        mode,
        period_months=period_months if mode in LIMITED_MODES else None,
    )
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO fnguide_crawls
                    (started_at, state, mode, report_limit, period_months, asset_id, debug)
                VALUES (%s, 'starting', %s, NULL, %s, %s, %s)
                RETURNING *
                """,
                (now, mode, period_months, asset_id, bool(debug)),
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


def _get_latest_error() -> dict[str, Any] | None:
    """If the newest crawl row is error, restart is blocked until SQL clears it."""
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
    return dict(row)


def _db_connect_info() -> dict[str, str]:
    """Non-secret connection details for unblock instructions."""
    url = database_url()
    parsed = urlparse(url)
    host = parsed.hostname or os.environ.get("POSTGRES_HOST", "")
    port = str(parsed.port or os.environ.get("POSTGRES_PORT", ""))
    db = (parsed.path or "/").lstrip("/") or os.environ.get("POSTGRES_DB", "")
    user = unquote(parsed.username or "") or os.environ.get("POSTGRES_USER", "")
    return {
        "host": host,
        "port": port,
        "database": db,
        "user": user,
    }


def _unblock_sql(crawl_id: str) -> str:
    return (
        "UPDATE fnguide_crawls "
        f"SET state = 'ended' "
        f"WHERE id = '{crawl_id}' AND state = 'error';"
    )


def _unblock_directions(crawl_id: str) -> dict[str, Any]:
    db = _db_connect_info()
    sql = _unblock_sql(crawl_id)
    return {
        "db": db,
        "unblock_sql": sql,
        "unblock_text": (
            f"# DB 접속 (비밀번호는 서버 .env 의 "
            f"POSTGRES_PASSWORD / DATABASE_URL 참고)\n"
            f"host={db['host']}\n"
            f"port={db['port']}\n"
            f"database={db['database']}\n"
            f"user={db['user']}\n"
            f"\n"
            f"# 재실행 허용: fnguide_crawls.state 를 error → ended\n"
            f"{sql}\n"
        ),
    }


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
    port = out.get("cdp_port")
    out["cdp_http_url"] = f"http://127.0.0.1:{port}" if port else None
    return out


def get_cdp_status() -> dict[str, Any]:
    """Summarize CDP endpoint for an open adhoc crawl."""
    reconcile_stale_crawls()
    row = _get_open_row()
    if not row:
        return {
            "ok": False,
            "status": 409,
            "message": "열린 크롤이 없습니다.",
        }
    crawl = _serialize(row)
    # After search debug handoff mode becomes adhoc; source adhoc also exposes CDP.
    if crawl.get("mode") not in CDP_STATUS_MODES and not crawl.get("debug"):
        return {
            "ok": False,
            "status": 409,
            "message": "adhoc/source-adhoc(또는 search debug) 크롤이 아닙니다.",
            "crawl": crawl,
        }
    port = crawl.get("cdp_port")
    if not port:
        return {
            "ok": False,
            "status": 503,
            "message": "CDP 포트가 아직 없습니다.",
            "crawl": crawl,
        }
    url = f"http://127.0.0.1:{port}"
    pages: list[Any] = []
    try:
        import urllib.request

        with urllib.request.urlopen(f"{url}/json/list", timeout=2) as resp:
            import json as _json

            pages = _json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {
            "ok": False,
            "status": 503,
            "message": f"CDP 연결 실패: {exc}",
            "crawl": crawl,
            "cdp_port": port,
            "cdp_http_url": url,
        }
    return {
        "ok": True,
        "crawl": crawl,
        "cdp_port": port,
        "cdp_http_url": url,
        "pages": [
            {
                "id": p.get("id"),
                "title": p.get("title"),
                "url": p.get("url"),
                "type": p.get("type"),
            }
            for p in pages
            if isinstance(p, dict)
        ],
    }
