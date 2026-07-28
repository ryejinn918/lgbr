"""Consensus run status, start, inputs, outputs, and compare-chat API."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from lgbr_api.db import connect, load_database_env

ROOT = Path(__file__).resolve().parents[3]
CONSENSUS_LOG = ROOT / ".consensus" / "consensus.log"
DEFAULT_EVENT_LIMIT = 50
DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_SEOUL = ZoneInfo("Asia/Seoul")

THEMES = frozenset(
    {
        "ai",
        "physical_ai",
        "appliance",
        "display",
        "automotive",
        "petrochemical",
    }
)
THEME_ABBREV = {
    # Legacy asset ids (cs-dc-*); not an active consensus theme.
    "datacenter": "dc",
    "ai": "ai",
    "physical_ai": "pai",
    "appliance": "ap",
    "display": "dp",
    "automotive": "am",
    "petrochemical": "pc",
}
DEFAULT_QUESTION = {
    "ai": "AI/AIDC, 지금 뭐 보면 돼?",
    "physical_ai": "피지컬 AI, 지금 뭐 보면 돼?",
    "appliance": "가전, 지금 뭐 보면 돼?",
    "display": "디스플레이, 지금 뭐 보면 돼?",
    "automotive": "자동차, 지금 뭐 보면 돼?",
    "petrochemical": "석유화학, 지금 뭐 보면 돼?",
}
STATE_LABELS = {
    "starting": "시작 중",
    "active": "실행 중",
    "stopping": "종료 중",
    "awaiting": "분석 축 확인 대기",
    "ended": "종료",
    "error": "오류",
    "idle": "대기",
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


def _make_asset_id(theme: str) -> str:
    abbrev = THEME_ABBREV[theme]
    day = datetime.now(_SEOUL).strftime("%y%m%d")
    return f"cs-{abbrev}-{day}-{secrets.token_hex(3)}"


def _parse_jsonb(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value


def _serialize_run(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    state = str(row.get("state") or "idle")
    progress = _parse_jsonb(row.get("progress") or {})
    if not isinstance(progress, dict):
        progress = {}
    criteria = _parse_jsonb(row.get("criteria") or {})
    if not isinstance(criteria, dict):
        criteria = {}
    return {
        "id": str(row["id"]),
        "asset_id": row.get("asset_id"),
        "theme": row.get("theme"),
        "question": row.get("question"),
        "model": row.get("model"),
        "state": state,
        "label": STATE_LABELS.get(state, state),
        "progress": progress,
        "criteria": criteria,
        "message": row.get("message"),
        "pid": row.get("pid"),
        "started_at": row["started_at"].isoformat() if row.get("started_at") else None,
        "ended_at": row["ended_at"].isoformat() if row.get("ended_at") else None,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "stop_requested_at": (
            row["stop_requested_at"].isoformat()
            if row.get("stop_requested_at")
            else None
        ),
    }


def reconcile_stale_runs() -> None:
    now = _now()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, pid, state, started_at
            FROM consensus_runs
            WHERE ended_at IS NULL
            """
        )
        for row in cur.fetchall():
            pid = row.get("pid")
            if pid is None:
                # Human review pause after thesis — not a dead worker.
                if row.get("state") == "awaiting":
                    continue
                started = row.get("started_at")
                age = 9999.0
                if isinstance(started, datetime):
                    age = (now - started.astimezone(timezone.utc)).total_seconds()
                if row.get("state") == "starting" and age < 60:
                    continue
                message = "consensus worker never claimed pid"
            elif _pid_alive(int(pid)):
                continue
            else:
                message = f"consensus worker pid {pid} is dead"
            cur.execute(
                """
                UPDATE consensus_runs
                SET state = 'error', ended_at = %s,
                    message = COALESCE(message, %s)
                WHERE id = %s AND ended_at IS NULL
                """,
                (now, message, row["id"]),
            )
        conn.commit()


def _get_open_row() -> dict[str, Any] | None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM consensus_runs
            WHERE ended_at IS NULL
            ORDER BY started_at DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _get_run_row(run_id: str | None) -> dict[str, Any] | None:
    with connect() as conn, conn.cursor() as cur:
        if run_id:
            cur.execute("SELECT * FROM consensus_runs WHERE id = %s::uuid", (run_id,))
        else:
            cur.execute(
                """
                SELECT * FROM consensus_runs
                ORDER BY COALESCE(ended_at, started_at) DESC NULLS LAST
                LIMIT 1
                """
            )
        row = cur.fetchone()
    return dict(row) if row else None


def list_events(run_id: str | None = None, *, limit: int = DEFAULT_EVENT_LIMIT) -> dict:
    limit = max(1, min(int(limit), 200))
    with connect() as conn, conn.cursor() as cur:
        if not run_id:
            cur.execute(
                """
                SELECT id::text FROM consensus_runs
                ORDER BY started_at DESC LIMIT 1
                """
            )
            row = cur.fetchone()
            if not row:
                return {"ok": True, "items": [], "run_id": None}
            run_id = row["id"]
        cur.execute(
            """
            SELECT id::text, run_id::text, at, level, stage, event, detail
            FROM consensus_run_events
            WHERE run_id = %s::uuid
            ORDER BY at DESC
            LIMIT %s
            """,
            (run_id, limit),
        )
        items = []
        for r in cur.fetchall():
            detail = r.get("detail") or {}
            items.append(
                {
                    "id": r["id"],
                    "run_id": r["run_id"],
                    "at": r["at"].isoformat() if r.get("at") else None,
                    "level": r["level"],
                    "stage": r["stage"],
                    "event": r["event"],
                    "detail": detail,
                }
            )
    return {"ok": True, "items": items, "run_id": run_id}


def get_current_run(
    *, run_id: str | None = None, event_limit: int = DEFAULT_EVENT_LIMIT
) -> dict[str, Any]:
    """Status for the open run, or a specific run when ``run_id`` is set.

    Without ``run_id``, only open rows (``ended_at IS NULL``) are current.
    After a worker finishes, this returns ``state=idle`` / ``run=null`` so the
    UI does not treat a finished run as still active. Pollers that need the
    terminal state must pass ``run_id`` (or use ``/latest`` / history).
    """
    reconcile_stale_runs()
    open_row = _get_open_row()
    if run_id:
        row = _get_run_row(run_id)
    else:
        # Idle must not surface a previous ended run as "current".
        row = open_row
    run = _serialize_run(row)
    can_start = open_row is None
    if open_row is None and run_id is None:
        state = "idle"
        events: list[Any] = []
        message = None
        progress: dict[str, Any] = {}
    else:
        state = run["state"] if run else "idle"
        events = list_events(run["id"] if run else None, limit=event_limit).get(
            "items"
        ) or []
        message = (run or {}).get("message")
        progress = (run or {}).get("progress") or {}
    return {
        "ok": True,
        "label": STATE_LABELS.get(state, state),
        "state": state,
        "run": run,
        "progress": progress,
        "events": events,
        "can_start": can_start,
        "message": message,
    }


def _normalize_theme(theme: str) -> str:
    """Legacy datacenter slug merges into ai (AI/AIDC)."""
    return "ai" if theme == "datacenter" else theme


def list_history(*, limit: int = 30, theme: str | None = None) -> dict[str, Any]:
    limit = max(1, min(int(limit), 100))
    if theme is not None:
        theme = _normalize_theme(theme)
    if theme is not None and theme not in THEMES:
        return {"ok": False, "status": 400, "message": "invalid theme", "items": []}
    with connect() as conn, conn.cursor() as cur:
        if theme:
            cur.execute(
                """
                SELECT id, asset_id, theme, question, model, state, message,
                       criteria, progress, started_at, ended_at, created_at
                FROM consensus_runs
                WHERE theme = %s
                ORDER BY COALESCE(ended_at, started_at) DESC NULLS LAST
                LIMIT %s
                """,
                (theme, limit),
            )
        else:
            cur.execute(
                """
                SELECT id, asset_id, theme, question, model, state, message,
                       criteria, progress, started_at, ended_at, created_at
                FROM consensus_runs
                ORDER BY COALESCE(ended_at, started_at) DESC NULLS LAST
                LIMIT %s
                """,
                (limit,),
            )
        items = [_serialize_run(dict(r)) for r in cur.fetchall()]
    return {"ok": True, "items": items, "theme": theme}


def get_latest_ended(*, theme: str) -> dict[str, Any]:
    """Latest ended run for a theme, including frame markdown bodies."""
    theme = _normalize_theme(theme)
    if theme not in THEMES:
        return {"ok": False, "status": 400, "message": "invalid theme", "run": None}
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM consensus_runs
            WHERE theme = %s AND state = 'ended'
            ORDER BY COALESCE(ended_at, started_at) DESC NULLS LAST
            LIMIT 1
            """,
            (theme,),
        )
        row = cur.fetchone()
    if not row:
        return {"ok": True, "theme": theme, "run": None, "filled_frame": None,
                "consensus_frame": None}
    run = _serialize_run(dict(row))
    assert run is not None
    out = get_outputs(run["id"])
    if not out.get("ok"):
        return {
            "ok": True,
            "theme": theme,
            "run": run,
            "filled_frame": None,
            "consensus_frame": None,
        }
    return {
        "ok": True,
        "theme": theme,
        "run": run,
        "filled_frame": out.get("filled_frame"),
        "consensus_frame": out.get("consensus_frame"),
    }


def _input_row(r: dict[str, Any], **extra: Any) -> dict[str, Any]:
    pub = r.get("published_at")
    return {
        "id": str(r["id"]),
        "source_key": r.get("source_key"),
        "title": r.get("title"),
        "provider": r.get("provider"),
        "page_count": r.get("page_count"),
        "published_at": pub.isoformat() if pub is not None else None,
        "quality_pass": r.get("quality_pass"),
        "quality_scope": r.get("quality_scope"),
        "theme_tag": r.get("theme"),
        "will_select": False,
        "will_fill_extra": False,
        "select_role": None,
        "select_why": None,
        "exclude_reason": None,
        **extra,
    }


def list_inputs(*, theme: str) -> dict[str, Any]:
    """List candidate reports for Ops. Pool only (no LLM); select runs at start."""
    theme = _normalize_theme(theme)
    if theme not in THEMES:
        return {"ok": False, "status": 400, "message": "invalid theme", "items": []}

    src = str(ROOT / "consensus" / "src")
    if src not in sys.path:
        sys.path.insert(0, src)

    from consensus.runs_store import (  # noqa: WPS433
        PERIOD_MONTHS_DEFAULT,
        list_pool_reports,
    )
    from consensus.select import pool_themes_for  # noqa: WPS433

    pool_themes = pool_themes_for(theme)
    pool = list_pool_reports(themes=pool_themes)
    items = [_input_row(r) for r in pool]
    qp_count = sum(1 for r in pool if r.get("quality_pass") is True)
    return {
        "ok": True,
        "theme": theme,
        "items": items,
        "selected_count": 0,
        "secondary_count": 0,
        "total": len(items),
        "criteria": {
            "theme": theme,
            "pool_themes": list(pool_themes),
            "period_months": PERIOD_MONTHS_DEFAULT,
            "quality_pass": True,
            "pool_count": len(items),
            "quality_pass_count": qp_count,
            "select": "on_run_start",
        },
    }


def get_outputs(run_id: str) -> dict[str, Any]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT kind, ordinal, body_md, body_json, created_at
            FROM consensus_outputs
            WHERE run_id = %s::uuid
            ORDER BY kind, ordinal
            """,
            (run_id,),
        )
        outputs = {}
        for r in cur.fetchall():
            outputs[r["kind"]] = {
                "kind": r["kind"],
                "ordinal": r["ordinal"],
                "body_md": r.get("body_md"),
                "body_json": r.get("body_json"),
                "created_at": (
                    r["created_at"].isoformat() if r.get("created_at") else None
                ),
            }
        cur.execute(
            "SELECT id::text, state, theme, asset_id FROM consensus_runs WHERE id=%s::uuid",
            (run_id,),
        )
        run = cur.fetchone()
    if not run:
        return {"ok": False, "status": 404, "message": "run not found"}
    return {
        "ok": True,
        "run_id": str(run["id"]),
        "state": run["state"],
        "theme": run["theme"],
        "asset_id": run["asset_id"],
        "filled_frame": (outputs.get("filled_frame") or {}).get("body_md"),
        "consensus_frame": (outputs.get("consensus_frame") or {}).get("body_md"),
        "fill_plan": (outputs.get("fill_plan") or {}).get("body_json"),
        "outputs": outputs,
    }


def get_run_docs(run_id: str) -> dict[str, Any]:
    """List run docs with metadata only (no compress_md bodies)."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.role, d.rank, d.doc_status, d.exclude_reason, d.select_why,
                   d.error,
                   r.id::text AS report_id, r.source_key, r.title,
                   r.page_count, r.quality_pass, r.quality_scope,
                   r.attrs->>'provider' AS provider,
                   a.id::text AS artifact_id,
                   (
                     a.compress_md IS NOT NULL
                     AND length(a.compress_md) > 0
                   ) AS has_compress,
                   a.slice_count,
                   a.toc_found
            FROM consensus_run_docs d
            JOIN reports r ON r.id = d.report_id
            LEFT JOIN consensus_doc_artifacts a ON a.id = d.artifact_id
            WHERE d.run_id = %s::uuid
            ORDER BY
              CASE d.role
                WHEN 'selected' THEN 0
                WHEN 'fill_extra' THEN 1
                ELSE 2
              END,
              d.rank NULLS LAST
            """,
            (run_id,),
        )
        items = []
        for r in cur.fetchall():
            row = dict(r)
            items.append(
                {
                    "role": row["role"],
                    "rank": row.get("rank"),
                    "doc_status": row["doc_status"],
                    "exclude_reason": row.get("exclude_reason"),
                    "select_why": row.get("select_why"),
                    "error": row.get("error"),
                    "report_id": row["report_id"],
                    "source_key": row["source_key"],
                    "title": row["title"],
                    "page_count": row.get("page_count"),
                    "quality_pass": row.get("quality_pass"),
                    "quality_scope": row.get("quality_scope"),
                    "provider": row.get("provider"),
                    "artifact_id": row.get("artifact_id"),
                    "has_compress": bool(row.get("has_compress")),
                    "slice_count": row.get("slice_count"),
                    "toc_found": row.get("toc_found"),
                }
            )
    return {"ok": True, "run_id": run_id, "items": items}


def get_run_doc_compress(run_id: str, report_id: str) -> dict[str, Any]:
    """Fetch one report's compress_md for a run (lazy body load)."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT r.id::text AS report_id, r.title,
                   a.compress_md, a.slice_count
            FROM consensus_run_docs d
            JOIN reports r ON r.id = d.report_id
            LEFT JOIN consensus_doc_artifacts a ON a.id = d.artifact_id
            WHERE d.run_id = %s::uuid
              AND d.report_id = %s::uuid
            LIMIT 1
            """,
            (run_id, report_id),
        )
        row = cur.fetchone()
    if not row:
        return {
            "ok": False,
            "status": 404,
            "message": "run doc not found",
            "run_id": run_id,
            "report_id": report_id,
        }
    md = row.get("compress_md")
    return {
        "ok": True,
        "run_id": run_id,
        "report_id": row["report_id"],
        "title": row.get("title"),
        "compress_md": md,
        "has_compress": bool(md),
        "slice_count": row.get("slice_count"),
    }


def _ensure_prompt_set(label: str | None = None) -> str:
    """FK/label only — prompt SSOT is consensus package code (not these rows)."""
    from consensus.runs_store import (  # noqa: WPS433
        DOC_PROMPT_SET_LABEL,
        ensure_prompt_set,
    )

    return ensure_prompt_set(
        label=label or DOC_PROMPT_SET_LABEL,
        notes="SSOT=consensus package code; DB prompts are placeholders (not loaded)",
    )

def _spawn_worker(run_id: str) -> None:
    python = ROOT / ".venv" / "bin" / "python"
    if not python.is_file():
        python = Path(sys.executable)
    CONSENSUS_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(CONSENSUS_LOG, "a", encoding="utf-8")  # noqa: SIM115
    log_f.write(f"\n--- consensus worker {_now().isoformat()} id={run_id} ---\n")
    log_f.flush()
    subprocess.Popen(
        [str(python), "-m", "consensus", "run", "--run-id", run_id],
        cwd=str(ROOT),
        stdout=log_f,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def start_run(
    *,
    theme: str,
    question: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    """Start thesis cut; always pauses at awaiting for axis review."""
    theme = _normalize_theme(theme)
    if theme not in THEMES:
        return {
            "ok": False,
            "status": 400,
            "message": (
                "theme must be ai, physical_ai, "
                "appliance, display, automotive, or petrochemical"
            ),
            "can_start": False,
            "run": None,
        }
    if until is not None and until not in ("thesis", "select"):
        return {
            "ok": False,
            "status": 400,
            "message": "until must be 'thesis', 'select', or omitted",
            "can_start": False,
            "run": None,
        }
    reconcile_stale_runs()
    open_row = _get_open_row()
    if open_row:
        run = _serialize_run(open_row)
        return {
            "ok": False,
            "status": 409,
            "message": "이미 컨센서스 런이 실행 중이거나 분석 축 확인 대기 중입니다.",
            "label": run["label"] if run else "busy",
            "can_start": False,
            "run": run,
        }

    q = (question or "").strip() or DEFAULT_QUESTION[theme]
    model = DEFAULT_MODEL
    # Fresh runs always cut axes first (until=thesis); select-only is via continue.
    criteria: dict[str, Any] = {
        "quality_pass": True,
        "theme": theme,
        "until": "thesis",
    }
    try:
        prompt_set_id = _ensure_prompt_set()
        asset_id = _make_asset_id(theme)
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO consensus_runs (
                    asset_id, prompt_set_id, theme, question, criteria, model, state
                )
                VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s, 'starting')
                RETURNING *
                """,
                (
                    asset_id,
                    prompt_set_id,
                    theme,
                    q,
                    json.dumps(criteria),
                    model,
                ),
            )
            row = dict(cur.fetchone())
            conn.commit()
    except Exception as exc:
        return {
            "ok": False,
            "status": 500,
            "message": f"run 생성 실패: {exc}",
            "can_start": False,
            "run": None,
        }

    run_id = str(row["id"])
    try:
        _spawn_worker(run_id)
    except Exception as exc:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE consensus_runs
                SET state='error', ended_at=now(), message=%s
                WHERE id=%s::uuid
                """,
                (f"spawn failed: {exc}", run_id),
            )
            conn.commit()
        return {
            "ok": False,
            "status": 500,
            "message": f"워커 기동 실패: {exc}",
            "can_start": True,
            "run": _serialize_run(row),
        }

    return {
        "ok": True,
        "status": 202,
        "message": "분석 축 잡기를 시작했습니다.",
        "label": "시작 중",
        "can_start": False,
        "run": _serialize_run(row),
    }


def _count_selected_docs(run_id: str) -> int:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)::int AS n
            FROM consensus_run_docs
            WHERE run_id = %s::uuid
              AND role IN ('selected', 'fill_extra')
            """,
            (run_id,),
        )
        row = cur.fetchone()
    return int((row or {}).get("n") or 0)


def continue_run(
    run_id: str,
    *,
    thesis: str | None = None,
    cut_logic: str | None = None,
    pillar_sketch: list[str] | None = None,
    until: str | None = None,
    resume_from: str | None = None,
) -> dict[str, Any]:
    """Resume awaiting→select, or ended select-only→doc/frame/fill."""
    if until is not None and until not in ("select",):
        return {
            "ok": False,
            "status": 400,
            "message": "until must be 'select' (stop after pack) or omitted (full)",
            "can_start": False,
            "run": None,
        }
    resume = (resume_from or "").strip() or None
    if resume is not None and resume not in ("select", "doc"):
        return {
            "ok": False,
            "status": 400,
            "message": "resume_from must be 'select', 'doc', or omitted",
            "can_start": False,
            "run": None,
        }
    reconcile_stale_runs()
    row = _get_run_row(run_id)
    if not row:
        return {
            "ok": False,
            "status": 404,
            "message": "런을 찾을 수 없습니다.",
            "can_start": False,
            "run": None,
        }

    state = str(row.get("state") or "")
    criteria = _parse_jsonb(row.get("criteria") or {})
    if not isinstance(criteria, dict):
        criteria = {}

    # Ended select-only (or error mid-doc with pack) → keep pack, run doc/frame/fill.
    if resume == "doc":
        return _continue_from_select_only(run_id, row=row, criteria=criteria)
    if (
        resume is None
        and state == "ended"
        and str(criteria.get("until") or "") == "select"
    ):
        return _continue_from_select_only(run_id, row=row, criteria=criteria)

    if state != "awaiting":
        return {
            "ok": False,
            "status": 409,
            "message": f"분석 축 확인 대기 상태가 아닙니다 (state={state}).",
            "can_start": False,
            "run": _serialize_run(row),
        }

    if thesis is not None:
        criteria["thesis"] = str(thesis).strip()
    if cut_logic is not None:
        criteria["cut_logic"] = str(cut_logic).strip()
    if pillar_sketch is not None:
        criteria["pillar_sketch"] = [
            str(p).strip() for p in pillar_sketch if str(p).strip()
        ]
    if not criteria.get("thesis") or len(criteria.get("pillar_sketch") or []) < 2:
        return {
            "ok": False,
            "status": 400,
            "message": "thesis와 pillar_sketch(2개 이상)가 필요합니다.",
            "can_start": False,
            "run": _serialize_run(row),
        }
    criteria["resume_from"] = "select"
    if until == "select":
        criteria["until"] = "select"
    else:
        criteria.pop("until", None)

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE consensus_runs
            SET state = 'starting',
                pid = NULL,
                started_at = now(),
                ended_at = NULL,
                stop_requested_at = NULL,
                message = NULL,
                criteria = %s::jsonb
            WHERE id = %s::uuid AND state = 'awaiting' AND ended_at IS NULL
            RETURNING id
            """,
            (json.dumps(criteria, ensure_ascii=False), run_id),
        )
        ok = cur.fetchone() is not None
        conn.commit()
    if not ok:
        return {
            "ok": False,
            "status": 409,
            "message": "런을 재개할 수 없습니다.",
            "can_start": False,
            "run": _serialize_run(row),
        }
    try:
        _spawn_worker(run_id)
    except Exception as exc:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE consensus_runs
                SET state='awaiting', message=%s
                WHERE id=%s::uuid
                """,
                (f"spawn failed: {exc}", run_id),
            )
            conn.commit()
        return {
            "ok": False,
            "status": 500,
            "message": f"워커 기동 실패: {exc}",
            "can_start": False,
            "run": _serialize_run(_get_run_row(run_id)),
        }
    return {
        "ok": True,
        "status": 202,
        "message": "축을 반영해 선별을 이어서 시작합니다.",
        "label": "시작 중",
        "can_start": False,
        "run": _serialize_run(_get_run_row(run_id)),
    }


def _continue_from_select_only(
    run_id: str,
    *,
    row: dict[str, Any],
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Reopen ended/error select pack and resume from doc stage."""
    state = str(row.get("state") or "")
    if state not in ("ended", "error"):
        return {
            "ok": False,
            "status": 409,
            "message": f"선별만 종료된 런이 아닙니다 (state={state}).",
            "can_start": False,
            "run": _serialize_run(row),
        }
    until = str(criteria.get("until") or "")
    # ended: require until=select. error mid-doc: until may already be cleared.
    if state == "ended" and until != "select":
        return {
            "ok": False,
            "status": 409,
            "message": "선별까지만 진행한 런만 논지까지 이을 수 있습니다.",
            "can_start": False,
            "run": _serialize_run(row),
        }
    outputs = get_outputs(run_id)
    if outputs.get("filled_frame") or outputs.get("consensus_frame"):
        return {
            "ok": False,
            "status": 409,
            "message": "이미 논지가 있는 런입니다.",
            "can_start": _get_open_row() is None,
            "run": _serialize_run(row),
        }
    if _count_selected_docs(run_id) < 1:
        return {
            "ok": False,
            "status": 400,
            "message": "선별된 보고서가 없어 논지를 이어갈 수 없습니다.",
            "can_start": False,
            "run": _serialize_run(row),
        }
    if _get_open_row() is not None:
        return {
            "ok": False,
            "status": 409,
            "message": "이미 컨센서스 런이 실행 중이거나 분석 축 확인 대기 중입니다.",
            "can_start": False,
            "run": _serialize_run(row),
        }
    if not criteria.get("thesis") or len(criteria.get("pillar_sketch") or []) < 2:
        return {
            "ok": False,
            "status": 400,
            "message": "thesis와 pillar_sketch(2개 이상)가 필요합니다.",
            "can_start": True,
            "run": _serialize_run(row),
        }

    next_criteria = dict(criteria)
    next_criteria["resume_from"] = "doc"
    next_criteria.pop("until", None)

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE consensus_runs
            SET state = 'starting',
                pid = NULL,
                started_at = now(),
                ended_at = NULL,
                stop_requested_at = NULL,
                message = NULL,
                criteria = %s::jsonb
            WHERE id = %s::uuid
              AND state IN ('ended', 'error')
              AND ended_at IS NOT NULL
            RETURNING id
            """,
            (json.dumps(next_criteria, ensure_ascii=False), run_id),
        )
        ok = cur.fetchone() is not None
        conn.commit()
    if not ok:
        return {
            "ok": False,
            "status": 409,
            "message": "런을 재개할 수 없습니다.",
            "can_start": False,
            "run": _serialize_run(row),
        }
    try:
        _spawn_worker(run_id)
    except Exception as exc:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE consensus_runs
                SET state='ended',
                    ended_at=now(),
                    message=%s,
                    criteria = (criteria - 'resume_from') || %s::jsonb
                WHERE id=%s::uuid
                """,
                (
                    f"spawn failed: {exc}",
                    json.dumps({"until": "select"}, ensure_ascii=False),
                    run_id,
                ),
            )
            conn.commit()
        return {
            "ok": False,
            "status": 500,
            "message": f"워커 기동 실패: {exc}",
            "can_start": True,
            "run": _serialize_run(_get_run_row(run_id)),
        }
    return {
        "ok": True,
        "status": 202,
        "message": "선별을 유지한 채 논지(요약·골격·살붙임)를 이어서 시작합니다.",
        "label": "시작 중",
        "can_start": False,
        "run": _serialize_run(_get_run_row(run_id)),
    }


def request_stop() -> dict[str, Any]:
    with connect() as conn, conn.cursor() as cur:
        # Cancel human-review pause immediately.
        cur.execute(
            """
            UPDATE consensus_runs
            SET state = 'ended',
                ended_at = now(),
                pid = NULL,
                message = COALESCE(message, '분석 축 확인에서 종료됨'),
                stop_requested_at = now()
            WHERE ended_at IS NULL AND state = 'awaiting'
            RETURNING *
            """
        )
        awaiting = cur.fetchone()
        if awaiting:
            conn.commit()
            return {
                "ok": True,
                "message": "분석 축 확인 대기를 종료했습니다.",
                "run": _serialize_run(dict(awaiting)),
                "can_start": True,
            }
        cur.execute(
            """
            UPDATE consensus_runs
            SET stop_requested_at = now(),
                state = CASE
                    WHEN state IN ('active', 'starting') THEN 'stopping'
                    ELSE state
                END
            WHERE ended_at IS NULL
            RETURNING *
            """
        )
        row = cur.fetchone()
        conn.commit()
    if not row:
        return {
            "ok": True,
            "message": "실행 중인 런이 없습니다.",
            "run": None,
            "can_start": True,
        }
    return {
        "ok": True,
        "message": "종료를 요청했습니다.",
        "run": _serialize_run(dict(row)),
        "can_start": False,
    }


def _openrouter_key() -> str:
    load_database_env()
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    return key


def _chat_completion(
    messages: list[dict[str, str]], *, model: str, temperature: float = 0.3
) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
        "reasoning": {"effort": "none"},
    }
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {_openrouter_key()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/lgbr",
            "X-Title": "lgbr-consensus-compare",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode())
    if data.get("error"):
        raise RuntimeError(json.dumps(data["error"], ensure_ascii=False))
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("empty choices")
    content = ((choices[0].get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("empty content")
    return content


def compare_chat(
    *,
    mode: str,
    messages: list[dict[str, Any]],
    run_id: str | None = None,
    theme: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    if mode not in {"plain", "grounded"}:
        return {"ok": False, "status": 400, "message": "mode must be plain or grounded"}
    if not isinstance(messages, list) or not messages:
        return {"ok": False, "status": 400, "message": "messages required"}
    clean: list[dict[str, str]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "")
        content = str(m.get("content") or "").strip()
        if role not in {"user", "assistant", "system"} or not content:
            continue
        clean.append({"role": role, "content": content})
    if not any(m["role"] == "user" for m in clean):
        return {"ok": False, "status": 400, "message": "at least one user message required"}

    use_model = (model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    sys_msgs: list[dict[str, str]] = []
    resolved_run_id = run_id
    resolved_theme = theme if theme in THEMES else None

    if mode == "grounded":
        if not resolved_run_id and resolved_theme:
            latest = get_latest_ended(theme=resolved_theme)
            if not latest.get("ok"):
                return latest
            run = latest.get("run")
            if not run:
                return {
                    "ok": False,
                    "status": 400,
                    "message": f"no ended run for theme={resolved_theme}",
                }
            resolved_run_id = str(run["id"])
            frame = latest.get("filled_frame") or latest.get("consensus_frame")
        elif resolved_run_id:
            out = get_outputs(resolved_run_id)
            if not out.get("ok"):
                return out
            if out.get("state") != "ended":
                return {
                    "ok": False,
                    "status": 400,
                    "message": f"run state is {out.get('state')}, need ended",
                }
            frame = out.get("filled_frame") or out.get("consensus_frame")
            resolved_theme = out.get("theme") or resolved_theme
        else:
            return {
                "ok": False,
                "status": 400,
                "message": "theme or run_id required for grounded",
            }
        if not frame:
            return {
                "ok": False,
                "status": 400,
                "message": "run has no filled_frame/consensus_frame yet",
            }
        sys_msgs.append(
            {
                "role": "system",
                "content": (
                    "You answer using the consensus filled frame below as primary context. "
                    "Prefer facts and structure from the frame; say when something is not "
                    "covered. Reply in Korean unless the user asks otherwise.\n\n"
                    f"--- CONSENSUS FRAME ---\n{frame}\n--- END FRAME ---"
                ),
            }
        )
    else:
        sys_msgs.append(
            {
                "role": "system",
                "content": (
                    "You are a helpful research assistant. "
                    "Reply in Korean unless the user asks otherwise. "
                    "No external consensus frame is provided."
                ),
            }
        )

    # Drop client system messages; we inject our own.
    user_chain = [m for m in clean if m["role"] != "system"]
    try:
        content = _chat_completion(sys_msgs + user_chain, model=use_model)
    except Exception as exc:
        return {"ok": False, "status": 500, "message": str(exc)}

    return {
        "ok": True,
        "mode": mode,
        "content": content,
        "run_id": resolved_run_id if mode == "grounded" else None,
        "theme": resolved_theme if mode == "grounded" else None,
        "model": use_model,
    }
