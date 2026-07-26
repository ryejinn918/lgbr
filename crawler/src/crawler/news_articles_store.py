"""Upsert list-expansion rows into news_articles (no body fill)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from crawler.db import connect


def upsert_list_item(
    *,
    source: str,
    source_key: str,
    title: str,
    url: str,
    published_at: datetime | None = None,
    publisher: str | None = None,
    attrs: dict[str, Any] | None = None,
) -> str:
    """Insert or refresh a catalog row. Returns 'inserted' | 'updated' | 'unchanged'."""
    now = datetime.now(timezone.utc)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, title, url, published_at, publisher, attrs
                FROM news_articles
                WHERE source = %s AND source_key = %s
                """,
                (source, source_key),
            )
            existing = cur.fetchone()
            if existing is None:
                cur.execute(
                    """
                    INSERT INTO news_articles (
                        source, source_key, title, url, published_at,
                        publisher, attrs, first_seen_at, last_seen_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                    """,
                    (
                        source,
                        source_key,
                        title,
                        url,
                        published_at,
                        publisher,
                        _json(attrs),
                        now,
                        now,
                    ),
                )
                conn.commit()
                return "inserted"

            cur.execute(
                """
                UPDATE news_articles
                SET title = %s,
                    url = %s,
                    published_at = COALESCE(%s, published_at),
                    publisher = COALESCE(%s, publisher),
                    attrs = COALESCE(attrs, '{}'::jsonb) || COALESCE(%s::jsonb, '{}'::jsonb),
                    last_seen_at = %s
                WHERE source = %s AND source_key = %s
                """,
                (
                    title,
                    url,
                    published_at,
                    publisher,
                    _json(attrs),
                    now,
                    source,
                    source_key,
                ),
            )
            conn.commit()
            return "updated"


def source_key_exists(source: str, source_key: str) -> bool:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM news_articles
                WHERE source = %s AND source_key = %s
                LIMIT 1
                """,
                (source, source_key),
            )
            return cur.fetchone() is not None


def _json(value: dict[str, Any] | None) -> str:
    import json

    return json.dumps(value or {}, ensure_ascii=False)
