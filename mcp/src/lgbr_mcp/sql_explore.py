"""Read-only SQL exploration via Postgres role lgbr_mcp_ro (no app table allowlist)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from lgbr_api.db import connect, database_url

MCP_RO_ROLE = "lgbr_mcp_ro"
DEFAULT_ROW_CAP = 100
SCHEMA_DOC = """\
# mcp_reports (read-only view for LGBR collect MCP)

Columns:
- id (uuid): report id — pass to get_report
- source (text): fnguide, pwc, accenture, kpmg, ey, deloitte, hbr, hbrkorea, bain, mckinsey, bcg
- source_key, title, status, has_file (bool; PDF is NOT available via MCP)
- provider: brokerage / house label when present
- themes (jsonb array of theme ids)
- published_at (date), page_count, last_seen_at
- quality: pass|fail|pending|unauditable; quality_pass (bool|null); quality_scope; quality_at
- short_title, summary, topic, framework_summary (from quality audit JSON)
- audit_kind: sell_side (fnguide) | summary (other sources)
- url: original web URL (citation). MCP never provides PDF download.

Examples:
  SELECT source, count(*) FROM mcp_reports GROUP BY 1 ORDER BY 2 DESC;
  SELECT id, title, source, published_at, short_title, left(summary, 200) AS summary_clip, url
    FROM mcp_reports
   WHERE summary ILIKE '%AI%'
     AND published_at >= DATE '2026-04-01'
   ORDER BY published_at DESC
   LIMIT 20;
  SELECT id, title, topic, framework_summary, url
    FROM mcp_reports
   WHERE audit_kind = 'sell_side' AND quality = 'pass' AND themes ? 'ai'
   LIMIT 20;
"""


def describe_schema() -> dict[str, Any]:
    return {
        "ok": True,
        "relation": "mcp_reports",
        "documentation": SCHEMA_DOC,
        "hint": (
            "Use standard SQL SELECT against mcp_reports only. "
            "PDF is not provided; use summary/quality fields and url."
        ),
    }


@contextmanager
def _ro_connection() -> Iterator[psycopg.Connection]:
    """Connect as app user then SET ROLE to lgbr_mcp_ro (DB enforces grants)."""
    # Ensure DATABASE_URL is loaded
    _ = database_url()
    with connect() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f"SET ROLE {MCP_RO_ROLE}")
            cur.execute("SET statement_timeout = '3s'")
        try:
            yield conn
        finally:
            try:
                with conn.cursor() as cur:
                    cur.execute("RESET ROLE")
            except Exception:
                pass


def run_sql(sql: str, *, row_cap: int = DEFAULT_ROW_CAP) -> dict[str, Any]:
    text = (sql or "").strip()
    if not text:
        return {"ok": False, "message": "empty sql", "rows": [], "row_count": 0}

    cap = max(1, min(int(row_cap), 200))
    try:
        with _ro_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(text)
                if cur.description is None:
                    return {
                        "ok": False,
                        "message": "no result set (writes/DDL are not allowed)",
                        "rows": [],
                        "row_count": 0,
                    }
                rows = cur.fetchmany(cap + 1)
    except psycopg.Error as exc:
        return {
            "ok": False,
            "message": str(exc).split("\n")[0][:400],
            "rows": [],
            "row_count": 0,
        }

    truncated = len(rows) > cap
    if truncated:
        rows = rows[:cap]

    out_rows: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        # Never surface file paths if somehow selected from elsewhere
        item.pop("file_path", None)
        item.pop("file_name", None)
        item.pop("pdf_url", None)
        out_rows.append(item)

    return {
        "ok": True,
        "rows": out_rows,
        "row_count": len(out_rows),
        "truncated": truncated,
        "row_cap": cap,
        "hint": (
            "Use id with get_report for full quality_json. "
            "url is the original web page; PDF is not provided."
        ),
    }
