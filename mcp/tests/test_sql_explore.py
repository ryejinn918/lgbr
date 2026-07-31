"""SQL explore helpers (schema doc + optional live RO role checks)."""

from __future__ import annotations

import os

import pytest
from lgbr_mcp.sql_explore import describe_schema, run_sql


def test_describe_schema_documents_mcp_reports() -> None:
    doc = describe_schema()
    assert doc["ok"] is True
    assert doc["relation"] == "mcp_reports"
    assert "PDF" in doc["documentation"] or "pdf" in doc["documentation"].lower()
    assert "url" in doc["documentation"]


@pytest.mark.skipif(
    not (os.environ.get("DATABASE_URL") or "").strip(),
    reason="DATABASE_URL not set",
)
def test_run_sql_ro_role_live() -> None:
    from pathlib import Path

    from dotenv import load_dotenv

    root = Path(__file__).resolve().parents[2]  # repo root
    load_dotenv(root / ".env", override=False)

    ok = run_sql(
        "SELECT id, title, url, has_file FROM mcp_reports LIMIT 3"
    )
    # Migration may not be applied yet in bare CI — accept either success or missing relation
    if not ok["ok"] and "mcp_reports" in (ok.get("message") or ""):
        pytest.skip("mcp_reports not migrated")
    assert ok["ok"] is True
    assert ok["row_count"] <= 3
    for row in ok["rows"]:
        assert "file_path" not in row
        assert "pdf_url" not in row

    denied = run_sql("SELECT id FROM reports LIMIT 1")
    assert denied["ok"] is False
