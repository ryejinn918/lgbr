#!/usr/bin/env python3
"""Batch quality-audit downloaded reports (sector-framework pass)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

# Allow `uv run python scripts/audit_report_quality.py` from crawler/
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crawler.quality_audit import (  # noqa: E402
    DEFAULT_CONCURRENCY,
    DEFAULT_MODEL,
    run_audit,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_job(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max reports to audit (default: all pending)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-audit even if quality_at is set",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Parallel OpenRouter requests (default {DEFAULT_CONCURRENCY})",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenRouter model id (default {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--theme",
        default=None,
        help=(
            "Limit to attrs.theme "
            "(datacenter|ai|physical_ai|appliance|display|automotive|petrochemical)"
        ),
    )
    parser.add_argument(
        "--report-id",
        default=None,
        help="Audit a single report UUID (implies that row only)",
    )
    parser.add_argument(
        "--job-file",
        default=None,
        help="Write job status JSON for the monitor API",
    )
    args = parser.parse_args()

    report_id: UUID | None = None
    if args.report_id:
        report_id = UUID(str(args.report_id))

    job_path = Path(args.job_file) if args.job_file else None
    base_job: dict[str, Any] = {
        "state": "active",
        "label": "감사 중",
        "pid": os.getpid(),
        "started_at": _now(),
        "ended_at": None,
        "message": None,
        "force": bool(args.force),
        "limit": args.limit,
        "theme": args.theme,
        "report_id": str(report_id) if report_id else None,
        "concurrency": args.concurrency,
        "model": args.model,
        "stats": None,
        "can_start": False,
    }
    _write_job(job_path, base_job)

    try:
        stats = asyncio.run(
            run_audit(
                force=args.force or report_id is not None,
                limit=args.limit,
                concurrency=args.concurrency,
                model=args.model,
                theme=args.theme,
                report_id=report_id,
            )
        )
        print("stats", stats)
        base_job.update(
            {
                "state": "ended",
                "label": "완료",
                "ended_at": _now(),
                "message": (
                    f"대상 {stats.get('candidates', 0)}건 · "
                    f"적합 {stats.get('pass', 0)} · "
                    f"부적합 {stats.get('reject', 0)} · "
                    f"추출실패 {stats.get('extract_fail', 0)} · "
                    f"API오류 {stats.get('fail_api', 0)}"
                ),
                "stats": stats,
                "can_start": True,
            }
        )
        _write_job(job_path, base_job)
    except Exception as exc:  # noqa: BLE001
        print(f"audit failed: {exc}", file=sys.stderr)
        base_job.update(
            {
                "state": "error",
                "label": "오류",
                "ended_at": _now(),
                "message": f"품질 감사 중 오류: {str(exc)[:480]}",
                "can_start": True,
            }
        )
        _write_job(job_path, base_job)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
