#!/usr/bin/env python3
"""Apply SQL migrations in db/migrations using DATABASE_URL."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def main() -> None:
    load_dotenv(ROOT / ".env", override=False)
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    files = sorted(MIGRATIONS.glob("*.sql"))
    if not files:
        raise SystemExit(f"No migrations in {MIGRATIONS}")
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            for path in files:
                cur.execute(
                    "SELECT 1 FROM schema_migrations WHERE filename = %s",
                    (path.name,),
                )
                if cur.fetchone():
                    print(f"skip {path.name}")
                    continue
                cur.execute(path.read_text(encoding="utf-8"))
                cur.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (%s)",
                    (path.name,),
                )
                print(f"apply {path.name}")
        conn.commit()


if __name__ == "__main__":
    main()
