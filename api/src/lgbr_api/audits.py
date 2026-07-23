"""Quality-audit job status and manual start for the monitor API."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

ROOT = Path(__file__).resolve().parents[3]
AUDIT_LOG = ROOT / ".crawler" / "audit.log"
JOB_PATH = ROOT / ".crawler" / "audit_job.json"
SCRIPT = ROOT / "crawler" / "scripts" / "audit_report_quality.py"

VALID_THEMES = frozenset({"datacenter", "ai", "physical_ai"})
DEFAULT_CONCURRENCY = 8
MIN_CONCURRENCY = 1
MAX_CONCURRENCY = 32
MAX_LIMIT = 500

_IDLE: dict[str, Any] = {
    "state": "idle",
    "label": "대기 중",
    "pid": None,
    "started_at": None,
    "ended_at": None,
    "message": None,
    "force": False,
    "limit": None,
    "theme": None,
    "report_id": None,
    "concurrency": DEFAULT_CONCURRENCY,
    "model": None,
    "stats": None,
    "can_start": True,
}


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


def _read_job() -> dict[str, Any]:
    if not JOB_PATH.is_file():
        return dict(_IDLE)
    try:
        data = json.loads(JOB_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(_IDLE)
    if not isinstance(data, dict):
        return dict(_IDLE)
    out = dict(_IDLE)
    out.update(data)
    return out


def _write_job(data: dict[str, Any]) -> None:
    JOB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = JOB_PATH.with_suffix(JOB_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(JOB_PATH)


def _reconcile(job: dict[str, Any]) -> dict[str, Any]:
    state = str(job.get("state") or "idle")
    if state not in {"starting", "active"}:
        job["can_start"] = True
        return job
    pid = job.get("pid")
    try:
        pid_i = int(pid) if pid is not None else None
    except (TypeError, ValueError):
        pid_i = None
    if state == "starting" and pid_i is None:
        started = job.get("started_at")
        age = 9999.0
        if isinstance(started, str):
            try:
                age = (
                    _now() - datetime.fromisoformat(started)
                ).total_seconds()
            except ValueError:
                age = 9999.0
        if age < 60:
            job["can_start"] = False
            return job
        job.update(
            {
                "state": "error",
                "label": "오류",
                "ended_at": _now().isoformat(),
                "message": job.get("message")
                or "품질 감사가 시작되지 않았습니다.",
                "can_start": True,
            }
        )
        _write_job(job)
        return job
    if pid_i is not None and _pid_alive(pid_i):
        job["can_start"] = False
        return job
    job.update(
        {
            "state": "error",
            "label": "오류",
            "ended_at": _now().isoformat(),
            "message": job.get("message")
            or "품질 감사가 비정상 종료되었습니다.",
            "can_start": True,
        }
    )
    _write_job(job)
    return job


def get_audit_status() -> dict[str, Any]:
    job = _reconcile(_read_job())
    return {
        "ok": True,
        "state": job.get("state") or "idle",
        "label": job.get("label") or "대기 중",
        "message": job.get("message"),
        "audit": job,
        "can_start": bool(job.get("can_start", True)),
    }


def start_audit(
    *,
    limit: Any = None,
    force: bool = False,
    theme: str | None = None,
    concurrency: Any = None,
    report_id: str | None = None,
) -> dict[str, Any]:
    theme_filter: str | None = None
    if theme and theme != "all":
        if theme not in VALID_THEMES:
            return {
                "ok": False,
                "status": 400,
                "state": "error",
                "label": "오류",
                "message": "테마는 데이터센터, AI, Physical AI 중 하나여야 합니다.",
                "audit": None,
                "can_start": True,
            }
        theme_filter = theme

    rid: str | None = None
    if report_id:
        try:
            rid = str(UUID(report_id))
        except (TypeError, ValueError):
            return {
                "ok": False,
                "status": 400,
                "state": "error",
                "label": "오류",
                "message": "리포트 번호가 올바르지 않습니다.",
                "audit": None,
                "can_start": True,
            }

    report_limit: int | None = None
    if limit is not None:
        try:
            report_limit = int(limit)
        except (TypeError, ValueError):
            return {
                "ok": False,
                "status": 400,
                "state": "error",
                "label": "오류",
                "message": "건수 제한은 숫자여야 합니다.",
                "audit": None,
                "can_start": True,
            }
        if report_limit < 1 or report_limit > MAX_LIMIT:
            return {
                "ok": False,
                "status": 400,
                "state": "error",
                "label": "오류",
                "message": f"건수 제한은 1–{MAX_LIMIT} 사이여야 합니다.",
                "audit": None,
                "can_start": True,
            }

    conc = DEFAULT_CONCURRENCY if concurrency is None else concurrency
    try:
        conc = int(conc)
    except (TypeError, ValueError):
        return {
            "ok": False,
            "status": 400,
            "state": "error",
            "label": "오류",
            "message": "동시 처리 수는 숫자여야 합니다.",
            "audit": None,
            "can_start": True,
        }
    if conc < MIN_CONCURRENCY or conc > MAX_CONCURRENCY:
        return {
            "ok": False,
            "status": 400,
            "state": "error",
            "label": "오류",
            "message": (
                f"동시 처리 수는 {MIN_CONCURRENCY}–{MAX_CONCURRENCY} 사이여야 합니다."
            ),
            "audit": None,
            "can_start": True,
        }

    current = _reconcile(_read_job())
    if str(current.get("state") or "") in {"starting", "active"}:
        return {
            "ok": False,
            "status": 409,
            "state": current.get("state"),
            "label": current.get("label") or "감사 중",
            "message": "이미 품질 감사가 실행 중입니다.",
            "audit": current,
            "can_start": False,
        }

    if not SCRIPT.is_file():
        return {
            "ok": False,
            "status": 500,
            "state": "error",
            "label": "오류",
            "message": "품질 감사 실행 파일을 찾을 수 없습니다.",
            "audit": None,
            "can_start": True,
        }

    python = ROOT / ".venv" / "bin" / "python"
    if not python.is_file():
        python = Path(sys.executable)

    job: dict[str, Any] = {
        "state": "starting",
        "label": "시작 중",
        "pid": None,
        "started_at": _now().isoformat(),
        "ended_at": None,
        "message": None,
        "force": bool(force) or rid is not None,
        "limit": report_limit,
        "theme": theme_filter,
        "report_id": rid,
        "concurrency": conc,
        "model": None,
        "stats": None,
        "can_start": False,
    }
    _write_job(job)

    cmd = [
        str(python),
        str(SCRIPT),
        "--concurrency",
        str(conc),
        "--job-file",
        str(JOB_PATH),
    ]
    if report_limit is not None:
        cmd.extend(["--limit", str(report_limit)])
    if job["force"]:
        cmd.append("--force")
    if theme_filter:
        cmd.extend(["--theme", theme_filter])
    if rid:
        cmd.extend(["--report-id", rid])

    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(AUDIT_LOG, "a", encoding="utf-8")  # noqa: SIM115
    try:
        log_f.write(f"\n--- audit start {_now().isoformat()} ---\n")
        log_f.flush()
        subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=os.environ.copy(),
        )
    except Exception as exc:
        log_f.close()
        job.update(
            {
                "state": "error",
                "label": "오류",
                "ended_at": _now().isoformat(),
                "message": f"품질 감사 시작에 실패했습니다: {exc}",
                "can_start": True,
            }
        )
        _write_job(job)
        return {
            "ok": False,
            "status": 500,
            "state": "error",
            "label": "오류",
            "message": f"품질 감사 시작에 실패했습니다: {exc}",
            "audit": job,
            "can_start": True,
        }

    return {
        "ok": True,
        "status": 202,
        "state": "starting",
        "label": "시작 중",
        "message": "품질 감사를 시작했습니다.",
        "audit": job,
        "can_start": False,
    }
