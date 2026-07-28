"""DB access for consensus runs / docs / outputs / artifacts / prompts."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from consensus.db import connect

THEMES = frozenset(
    {
        "datacenter",
        "ai",
        "physical_ai",
        "appliance",
        "display",
        "automotive",
        "petrochemical",
    }
)
DEFAULT_QUESTION = {
    "datacenter": "데이터센터, 지금 뭐 보면 돼?",
    "ai": "AI, 지금 뭐 보면 돼?",
    "physical_ai": "피지컬 AI, 지금 뭐 보면 돼?",
    "appliance": "가전, 지금 뭐 보면 돼?",
    "display": "디스플레이, 지금 뭐 보면 돼?",
    "automotive": "자동차, 지금 뭐 보면 돼?",
    "petrochemical": "석유화학, 지금 뭐 보면 돼?",
}
# Consensus pool: only reports with published_at within this many calendar months.
PERIOD_MONTHS_DEFAULT = 3


def ensure_prompt_set(*, label: str, notes: str = "") -> str:
    """Create a prompt_set row for run FK / labeling only.

    SSOT for prompt text is the consensus package modules (toc/compress/frame/fill),
    not ``consensus_prompts`` rows. DB stage rows are placeholders so schema stays
    ready for a future prompt-set editor; the worker never loads them.
    """
    stages = (
        "toc",
        "local_compress",
        "report_compress",
        "consensus",
        "reduce",
        "fill_plan",
        "fill",
    )
    note = notes or (
        "SSOT=consensus package code; DB prompts are placeholders (not loaded at runtime)"
    )
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO consensus_prompt_sets (label, notes)
            VALUES (%s, %s)
            RETURNING id::text
            """,
            (label, note),
        )
        set_id = cur.fetchone()["id"]
        for stage in stages:
            cur.execute(
                """
                INSERT INTO consensus_prompts
                    (prompt_set_id, stage, system_text, user_template, params)
                VALUES (%s::uuid, %s, %s, %s, %s::jsonb)
                """,
                (
                    set_id,
                    stage,
                    f"[SSOT=code] {stage} system — consensus package, not this row",
                    f"[SSOT=code] {stage} user — consensus package, not this row",
                    json.dumps({"temperature": 0.2, "ssot": "code"}),
                ),
            )
        conn.commit()
    return set_id


def create_run(
    *,
    asset_id: str,
    prompt_set_id: str,
    theme: str,
    question: str,
    criteria: dict[str, Any],
    model: str,
) -> str:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO consensus_runs (
                asset_id, prompt_set_id, theme, question, criteria, model, state
            )
            VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s, 'starting')
            RETURNING id::text
            """,
            (
                asset_id,
                prompt_set_id,
                theme,
                question,
                json.dumps(criteria, ensure_ascii=False),
                model,
            ),
        )
        run_id = cur.fetchone()["id"]
        conn.commit()
    return run_id


def claim_run(run_id: str, *, pid: int) -> dict[str, Any] | None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE consensus_runs
            SET state = 'active', pid = %s
            WHERE id = %s::uuid AND state IN ('starting', 'active') AND ended_at IS NULL
            RETURNING id::text, asset_id, prompt_set_id::text, theme, question,
                      criteria, model, state, progress
            """,
            (pid, run_id),
        )
        row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def get_run(run_id: str) -> dict[str, Any] | None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text, asset_id, prompt_set_id::text, theme, question,
                   criteria, model, state, progress, message, ended_at
            FROM consensus_runs WHERE id = %s::uuid
            """,
            (run_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def end_run(run_id: str, *, state: str, message: str | None = None) -> None:
    if state not in {"ended", "error"}:
        raise ValueError(state)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE consensus_runs
            SET state = %s, ended_at = now(), message = COALESCE(%s, message), pid = NULL
            WHERE id = %s::uuid
            """,
            (state, message, run_id),
        )
        conn.commit()


def update_progress(run_id: str, fields: dict[str, Any]) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE consensus_runs
            SET progress = COALESCE(progress, '{}'::jsonb) || %s::jsonb
            WHERE id = %s::uuid
            """,
            (Jsonb(fields), run_id),
        )
        conn.commit()


def append_event(
    run_id: str,
    *,
    level: str,
    stage: str,
    event: str,
    detail: dict[str, Any] | None = None,
) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO consensus_run_events (run_id, level, stage, event, detail)
            VALUES (%s::uuid, %s, %s, %s, %s::jsonb)
            """,
            (run_id, level, stage, event, Jsonb(detail or {})),
        )
        conn.commit()


def list_theme_reports(theme: str) -> list[dict[str, Any]]:
    return list_pool_reports(themes=(theme,))


def list_pool_reports(
    *,
    themes: tuple[str, ...],
    period_months: int = PERIOD_MONTHS_DEFAULT,
) -> list[dict[str, Any]]:
    """Downloaded reports with attrs.theme in themes (qp first).

    Only includes rows with published_at within the last ``period_months``
    calendar months (NULL published_at excluded).
    """
    if not themes:
        return []
    months = max(1, int(period_months))
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, source_key, title, file_path, file_name, page_count,
                   published_at, quality_pass, quality_scope, quality_json, attrs,
                   attrs->>'provider' AS provider,
                   attrs->>'theme' AS theme
            FROM reports
            WHERE status = 'downloaded'
              AND attrs->>'theme' = ANY(%s)
              AND coalesce(file_path, '') <> ''
              AND published_at IS NOT NULL
              AND published_at >= (CURRENT_DATE - make_interval(months => %s))
            ORDER BY
              CASE WHEN quality_pass IS TRUE THEN 0 ELSE 1 END,
              published_at DESC NULLS LAST,
              page_count DESC NULLS LAST
            """,
            (list(themes), months),
        )
        return [dict(r) for r in cur.fetchall()]


def insert_run_docs(
    run_id: str,
    *,
    selected: list[dict[str, Any]],
    excluded: list[tuple[dict[str, Any], str]],
) -> None:
    with connect() as conn, conn.cursor() as cur:
        for i, r in enumerate(selected, start=1):
            role = str(r.get("select_role") or "selected")
            if role not in ("selected", "fill_extra"):
                role = "selected"
            why = r.get("select_why")
            why_s = str(why).strip() if why is not None else None
            if why_s == "":
                why_s = None
            cur.execute(
                """
                INSERT INTO consensus_run_docs
                    (run_id, report_id, role, rank, select_why, doc_status)
                VALUES (%s::uuid, %s, %s, %s, %s, 'pending')
                """,
                (run_id, r["id"], role, i, why_s),
            )
        for r, reason in excluded:
            cur.execute(
                """
                INSERT INTO consensus_run_docs
                    (run_id, report_id, role, exclude_reason, doc_status)
                VALUES (%s::uuid, %s, 'excluded', %s, 'pending')
                """,
                (run_id, r["id"], reason),
            )
        conn.commit()


def update_run_doc(
    run_id: str,
    report_id: UUID | str,
    *,
    doc_status: str,
    artifact_id: str | None = None,
    error: str | None = None,
) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE consensus_run_docs
            SET doc_status = %s,
                artifact_id = COALESCE(%s::uuid, artifact_id),
                error = %s
            WHERE run_id = %s::uuid AND report_id = %s
            """,
            (doc_status, artifact_id, error, run_id, report_id),
        )
        conn.commit()


def find_artifact(
    *,
    report_id: str,
    content_hash: str,
    prompt_set_id: str,
    model: str,
) -> dict[str, Any] | None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text, compress_md, toc_found, slice_count, status, meta
            FROM consensus_doc_artifacts
            WHERE report_id = %s
              AND content_hash = %s
              AND prompt_set_id = %s::uuid
              AND model = %s
              AND status = 'ok'
            """,
            (report_id, content_hash, prompt_set_id, model),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def upsert_artifact(
    *,
    report_id: str,
    content_hash: str,
    prompt_set_id: str,
    model: str,
    status: str,
    compress_md: str | None,
    toc_found: bool | None,
    slice_count: int | None,
    meta: dict[str, Any] | None = None,
) -> str:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO consensus_doc_artifacts (
                report_id, content_hash, prompt_set_id, model, status,
                toc_found, slice_count, compress_md, meta, updated_at
            )
            VALUES (
                %s, %s, %s::uuid, %s, %s, %s, %s, %s, %s::jsonb, now()
            )
            ON CONFLICT (report_id, content_hash, prompt_set_id, model)
            DO UPDATE SET
                status = EXCLUDED.status,
                toc_found = EXCLUDED.toc_found,
                slice_count = EXCLUDED.slice_count,
                compress_md = EXCLUDED.compress_md,
                meta = EXCLUDED.meta,
                updated_at = now()
            RETURNING id::text
            """,
            (
                report_id,
                content_hash,
                prompt_set_id,
                model,
                status,
                toc_found,
                slice_count,
                compress_md,
                json.dumps(meta or {}, ensure_ascii=False),
            ),
        )
        aid = cur.fetchone()["id"]
        conn.commit()
    return aid


def save_output(
    run_id: str,
    *,
    kind: str,
    body_md: str | None = None,
    body_json: dict[str, Any] | None = None,
    ordinal: int = 0,
) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO consensus_outputs (run_id, kind, ordinal, body_md, body_json)
            VALUES (%s::uuid, %s, %s, %s, %s)
            ON CONFLICT (run_id, kind, ordinal)
            DO UPDATE SET body_md = EXCLUDED.body_md, body_json = EXCLUDED.body_json
            """,
            (
                run_id,
                kind,
                ordinal,
                body_md,
                Jsonb(body_json) if body_json is not None else None,
            ),
        )
        conn.commit()


def get_output(run_id: str, kind: str, *, ordinal: int = 0) -> dict[str, Any] | None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT kind, ordinal, body_md, body_json, created_at
            FROM consensus_outputs
            WHERE run_id = %s::uuid AND kind = %s AND ordinal = %s
            """,
            (run_id, kind, ordinal),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def list_selected_docs_for_refill(run_id: str) -> list[dict[str, Any]]:
    """Core + bibliography run docs with report paths + compress artifact."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                d.report_id::text AS report_id,
                d.role,
                d.rank,
                d.doc_status,
                d.artifact_id::text AS artifact_id,
                r.source_key,
                r.title,
                r.attrs->>'provider' AS provider,
                r.published_at,
                r.file_path,
                a.compress_md,
                a.content_hash,
                a.slice_count,
                a.toc_found
            FROM consensus_run_docs d
            JOIN reports r ON r.id = d.report_id
            LEFT JOIN consensus_doc_artifacts a ON a.id = d.artifact_id
            WHERE d.run_id = %s::uuid
              AND d.role IN ('selected', 'fill_extra')
            ORDER BY
              CASE d.role WHEN 'selected' THEN 0 ELSE 1 END,
              d.rank NULLS LAST,
              r.published_at DESC NULLS LAST
            """,
            (run_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def touch_run_message(run_id: str, message: str) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE consensus_runs SET message = %s WHERE id = %s::uuid
            """,
            (message, run_id),
        )
        conn.commit()
