"""Durable PostgreSQL-backed dispatchers for crawl and consensus jobs."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lgbr_api.db import connect, load_database_env
from lgbr_api.processes import pid_is_alive

ROOT = Path(__file__).resolve().parents[3]
MAX_ATTEMPTS = 3
POLL_SECONDS = 2.0
_NON_RETRYABLE = (
    "no quality_pass",
    "no usable",
    "missing pdf",
    "unreadable pdf",
    "invalid theme",
    "invalid mode",
    "authentication failed",
    "password",
    "is not set",
)
_stop = False
_child: subprocess.Popen[Any] | None = None


def _log(message: str) -> None:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[{stamp}] {message}", flush=True)


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _attempt(row: dict[str, Any]) -> int:
    try:
        return int(_json_dict(row.get("progress")).get("worker_attempt") or 0)
    except (TypeError, ValueError):
        return 0


def _retryable(message: Any) -> bool:
    text = str(message or "").lower()
    return not any(marker in text for marker in _NON_RETRYABLE)


def _table(kind: str) -> str:
    return "fnguide_crawls" if kind == "crawl" else "consensus_runs"


def _open_job(kind: str) -> dict[str, Any] | None:
    table = _table(kind)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT * FROM {table}
            WHERE ended_at IS NULL
              AND state IN ('starting', 'active', 'stopping')
            ORDER BY started_at ASC
            LIMIT 1
            """
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _job(kind: str, job_id: str) -> dict[str, Any] | None:
    table = _table(kind)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {table} WHERE id=%s::uuid", (job_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def _close_crawl_session(cur: Any, session_id: Any) -> None:
    if not session_id:
        return
    cur.execute(
        """
        UPDATE fnguide_sessions
        SET state='error', ended_at=COALESCE(ended_at, now()),
            end_reason=COALESCE(end_reason, 'worker_retry'), pid=NULL,
            lease_until=NULL, logout_requested_at=NULL
        WHERE id=%s::uuid AND ended_at IS NULL
        """,
        (str(session_id),),
    )


def _reset_for_retry(kind: str, row: dict[str, Any], reason: str) -> bool:
    attempt = _attempt(row)
    if attempt >= MAX_ATTEMPTS or not _retryable(row.get("message") or reason):
        return False
    job_id = str(row["id"])
    with connect() as conn, conn.cursor() as cur:
        if kind == "crawl":
            _close_crawl_session(cur, row.get("session_id"))
            cur.execute(
                """
                UPDATE fnguide_crawls
                SET state='starting', ended_at=NULL, stop_requested_at=NULL,
                    pid=NULL, session_id=NULL, cdp_port=NULL,
                    message=%s
                WHERE id=%s::uuid
                  AND state IN ('starting', 'active', 'error')
                """,
                (f"worker retry queued: {reason}", job_id),
            )
        else:
            cur.execute(
                """
                UPDATE consensus_runs
                SET state='starting', ended_at=NULL, stop_requested_at=NULL,
                    pid=NULL, started_at=now(), message=%s
                WHERE id=%s::uuid
                  AND state IN ('starting', 'active', 'error')
                """,
                (f"worker retry queued: {reason}", job_id),
            )
        changed = cur.rowcount == 1
        conn.commit()
    if changed:
        _log(f"{kind} {job_id} queued for retry after attempt {attempt}: {reason}")
    return changed


def _finish_orphan(kind: str, row: dict[str, Any], message: str) -> None:
    table = _table(kind)
    with connect() as conn, conn.cursor() as cur:
        if kind == "crawl":
            _close_crawl_session(cur, row.get("session_id"))
        cur.execute(
            f"""
            UPDATE {table}
            SET state='error', ended_at=now(), pid=NULL, message=%s
            WHERE id=%s::uuid AND ended_at IS NULL
            """,
            (message, str(row["id"])),
        )
        conn.commit()


def _recover_or_get(kind: str) -> dict[str, Any] | None:
    row = _open_job(kind)
    if row is None:
        return None
    state = str(row.get("state") or "")
    pid = row.get("pid")
    if state == "stopping":
        if pid is None or not pid_is_alive(int(pid)):
            _finish_orphan(kind, row, "worker stopped while cancellation was pending")
        return None
    if pid is not None and pid_is_alive(int(pid)):
        return None
    if state == "starting" and pid is None:
        return row
    reason = f"orphaned {state} worker pid={pid}"
    if _reset_for_retry(kind, row, reason):
        return _open_job(kind)
    _finish_orphan(kind, row, f"{reason}; retry limit reached")
    return None


def _mark_attempt(kind: str, job_id: str, attempt: int) -> None:
    table = _table(kind)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE {table}
            SET progress = COALESCE(progress, '{{}}'::jsonb)
                || jsonb_build_object(
                    'worker_attempt', %s,
                    'worker_max_attempts', %s,
                    'worker_dispatched_at', now()
                ),
                message = %s
            WHERE id=%s::uuid AND state='starting' AND ended_at IS NULL
            """,
            (attempt, MAX_ATTEMPTS, f"worker attempt {attempt}/{MAX_ATTEMPTS}", job_id),
        )
        if cur.rowcount != 1:
            raise RuntimeError(f"cannot dispatch {kind} job {job_id}")
        conn.commit()


def _command(kind: str, job_id: str) -> list[str]:
    if kind == "crawl":
        return [
            sys.executable,
            "-m",
            "crawler",
            "crawl",
            "run",
            "--headless",
            "--crawl-id",
            job_id,
        ]
    return [sys.executable, "-m", "consensus", "run", "--run-id", job_id]


def _run_job(kind: str, row: dict[str, Any]) -> None:
    global _child
    job_id = str(row["id"])
    attempt = _attempt(row) + 1
    _mark_attempt(kind, job_id, attempt)
    log_dir = ROOT / (".crawler" if kind == "crawl" else ".consensus")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / ("crawl.log" if kind == "crawl" else "consensus.log")
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    _log(f"dispatch {kind} {job_id} attempt={attempt}")
    with log_path.open("a", encoding="utf-8") as log_f:
        log_f.write(f"\n--- durable worker {kind} id={job_id} attempt={attempt} ---\n")
        log_f.flush()
        _child = subprocess.Popen(
            _command(kind, job_id),
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            env=env,
        )
        while _child.poll() is None and not _stop:
            time.sleep(0.5)
        if _stop and _child.poll() is None:
            _child.terminate()
        return_code = _child.wait()
        _child = None
    latest = _job(kind, job_id)
    if latest and str(latest.get("state")) == "error":
        if _reset_for_retry(kind, latest, f"child exit={return_code}"):
            time.sleep(min(30, 5 * attempt))
            return
    _log(f"finished {kind} {job_id} exit={return_code} state={(latest or {}).get('state')}")


def _on_signal(_signum: int, _frame: Any) -> None:
    global _stop
    _stop = True
    if _child is not None and _child.poll() is None:
        _child.terminate()


def run(kind: str, *, once: bool = False) -> None:
    load_database_env()
    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)
    _log(f"{kind} durable worker started")
    while not _stop:
        try:
            row = _recover_or_get(kind)
            if row is not None:
                _run_job(kind, row)
                if once:
                    return
                continue
        except Exception as exc:
            _log(f"worker loop error: {exc}")
        if once:
            return
        time.sleep(POLL_SECONDS)
    _log(f"{kind} durable worker stopped")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="lgbr-job-worker")
    parser.add_argument("--kind", choices=("crawl", "consensus"), required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    run(args.kind, once=args.once)


if __name__ == "__main__":
    main()