"""Persistence helpers for attaching external reports to Consensus axes."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb

from lgbr_api.db import connect

RELATIONS = frozenset({"corroboration", "dissent", "supplement"})


def _json_value(value: Any) -> Any:
    """Convert PostgreSQL date/time values into JSON-safe values."""
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value

def _json_row(row: Any) -> dict[str, Any]:
    return {key: _json_value(value) for key, value in dict(row).items()}
EXTERNAL_SOURCES = (
    "pwc",
    "accenture",
    "kpmg",
    "ey",
    "deloitte",
    "bain",
    "bcg",
    "hbr",
    "hbrkorea",
)


def list_candidates(*, run_id: str, axis_index: int) -> dict[str, Any]:
    """Return quality-passed external reports not yet linked to an axis."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT r.id::text AS report_id, r.source, r.title,
                   r.published_at, r.page_count,
                   r.attrs->>'provider' AS provider,
                   r.quality_pass, r.quality_scope,
                   r.quality_json
            FROM reports r
            WHERE r.source = ANY(%s)
              AND r.quality_pass IS TRUE
              AND r.file_path IS NOT NULL
              AND NOT EXISTS (
                SELECT 1
                FROM consensus_axis_external_docs x
                WHERE x.run_id = %s::uuid
                  AND x.axis_index = %s
                  AND x.report_id = r.id
              )
            ORDER BY r.published_at DESC NULLS LAST, r.downloaded_at DESC
            LIMIT 100
            """,
            (list(EXTERNAL_SOURCES), run_id, axis_index),
        )
        return {"ok": True, "run_id": run_id, "axis_index": axis_index, "items": [_json_row(row) for row in cur.fetchall()]}


def list_links(*, run_id: str, axis_index: int | None = None) -> dict[str, Any]:
    """Return external evidence already attached to a Consensus run."""
    params: list[Any] = [run_id]
    axis_clause = ""
    if axis_index is not None:
        axis_clause = " AND x.axis_index = %s"
        params.append(axis_index)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT x.run_id::text AS run_id, x.axis_index, x.axis_label,
                   x.report_id::text AS report_id, x.relation,
                   x.select_reason, x.ai_confidence, x.ai_reason, x.review_state, x.created_at, x.updated_at,
                   r.source, r.title, r.published_at,
                   r.attrs->>'provider' AS provider
            FROM consensus_axis_external_docs x
            JOIN reports r ON r.id = x.report_id
            WHERE x.run_id = %s::uuid{axis_clause}
            ORDER BY x.axis_index, x.relation, r.published_at DESC NULLS LAST
            """,
            tuple(params),
        )
        return {"ok": True, "run_id": run_id, "items": [_json_row(row) for row in cur.fetchall()]}


def upsert_link(
    *,
    run_id: str,
    axis_index: int,
    axis_label: str,
    report_id: str,
    relation: str,
    select_reason: str | None = None,
) -> dict[str, Any]:
    """Attach one external report to one axis, replacing its classification."""
    relation = relation.strip().lower()
    if relation not in RELATIONS:
        raise ValueError(f"relation must be one of: {', '.join(sorted(RELATIONS))}")
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO consensus_axis_external_docs
                (run_id, axis_index, axis_label, report_id, relation, select_reason)
            VALUES (%s::uuid, %s, %s, %s::uuid, %s, %s)
            ON CONFLICT (run_id, axis_index, report_id) DO UPDATE SET
                axis_label = EXCLUDED.axis_label,
                relation = EXCLUDED.relation,
                select_reason = EXCLUDED.select_reason,
                updated_at = now()
            RETURNING run_id::text AS run_id, axis_index, axis_label,
                      report_id::text AS report_id, relation, select_reason
            """,
            (run_id, axis_index, axis_label.strip(), report_id, relation, select_reason),
        )
        row = _json_row(cur.fetchone())
        conn.commit()
    return {"ok": True, "item": row}


def remove_link(*, run_id: str, axis_index: int, report_id: str) -> dict[str, Any]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM consensus_axis_external_docs
            WHERE run_id = %s::uuid AND axis_index = %s AND report_id = %s::uuid
            RETURNING report_id::text AS report_id
            """,
            (run_id, axis_index, report_id),
        )
        row = cur.fetchone()
        conn.commit()
    return {"ok": True, "deleted": row is not None, "report_id": report_id}


