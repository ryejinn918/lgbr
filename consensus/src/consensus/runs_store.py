"""DB access for consensus runs / docs / outputs / artifacts / prompts."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from consensus.db import connect

THEMES = frozenset({"datacenter", "ai", "physical_ai"})
DEFAULT_QUESTION = {
    "datacenter": "데이터센터, 지금 뭐 보면 돼?",
    "ai": "AI, 지금 뭐 보면 돼?",
    "physical_ai": "Physical AI, 지금 뭐 보면 돼?",
}


def ensure_prompt_set(*, label: str, notes: str = "") -> str:
    """Insert a prompt_set with placeholder stage rows (runtime uses code prompts)."""
    stages = (
        "toc",
        "local_compress",
        "report_compress",
        "consensus",
        "reduce",
        "fill_plan",
        "fill",
    )
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO consensus_prompt_sets (label, notes)
            VALUES (%s, %s)
            RETURNING id::text
            """,
            (label, notes),
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
                    f"[runtime] {stage} system — see consensus package code",
                    f"[runtime] {stage} user — see consensus package code",
                    json.dumps({"temperature": 0.2}),
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
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, source_key, title, file_path, file_name, page_count,
                   published_at, quality_pass, quality_scope,
                   attrs->>'provider' AS provider
            FROM reports
            WHERE status = 'downloaded'
              AND attrs->>'theme' = %s
              AND coalesce(file_path, '') <> ''
            ORDER BY
              CASE WHEN quality_pass IS TRUE THEN 0 ELSE 1 END,
              published_at DESC NULLS LAST,
              page_count DESC NULLS LAST
            """,
            (theme,),
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
            cur.execute(
                """
                INSERT INTO consensus_run_docs
                    (run_id, report_id, role, rank, doc_status)
                VALUES (%s::uuid, %s, 'selected', %s, 'pending')
                """,
                (run_id, r["id"], i),
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
