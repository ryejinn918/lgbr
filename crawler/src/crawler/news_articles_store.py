"""Upsert list-expansion rows and body fill into news_articles."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

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


def list_pending_bodies(source: str, *, limit: int = 200) -> list[dict[str, Any]]:
    """Rows needing body fetch or (for nikkei) Korean brief re-summary.

    Pending when ``body_text`` is NULL, or when source is nikkei and
    ``attrs.summarized_at`` is missing (full text left from earlier runs).
    """
    limit = max(1, min(int(limit), 1000))
    src = str(source or "").strip().lower()
    with connect() as conn:
        with conn.cursor() as cur:
            if src == "nikkei":
                # Prefer re-summarize (stored raw body, no summarized_at) before
                # fresh browser extracts so legacy full-text rows are not starved.
                cur.execute(
                    """
                    SELECT id, source, source_key, title, url, published_at,
                           attrs, body_text
                    FROM news_articles
                    WHERE source = %s
                      AND (
                        body_text IS NULL
                        OR COALESCE(attrs->>'summarized_at', '') = ''
                      )
                    ORDER BY
                      CASE
                        WHEN body_text IS NOT NULL
                         AND COALESCE(attrs->>'summarized_at', '') = ''
                        THEN 0
                        ELSE 1
                      END,
                      published_at DESC NULLS LAST,
                      last_seen_at DESC
                    LIMIT %s
                    """,
                    (src, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, source, source_key, title, url, published_at,
                           attrs, body_text
                    FROM news_articles
                    WHERE source = %s AND body_text IS NULL
                    ORDER BY published_at DESC NULLS LAST, last_seen_at DESC
                    LIMIT %s
                    """,
                    (src, limit),
                )
            return [dict(r) for r in cur.fetchall()]


def list_missing_title_ko(
    source: str, *, limit: int = 200
) -> list[dict[str, Any]]:
    """Rows whose attrs lack a non-empty title_ko."""
    limit = max(1, min(int(limit), 1000))
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, source, source_key, title, attrs
                FROM news_articles
                WHERE source = %s
                  AND COALESCE(NULLIF(TRIM(attrs->>'title_ko'), ''), '') = ''
                ORDER BY published_at DESC NULLS LAST, last_seen_at DESC
                LIMIT %s
                """,
                (str(source).strip().lower(), limit),
            )
            return [dict(r) for r in cur.fetchall()]


def merge_attrs(
    article_id: UUID | str,
    attrs: dict[str, Any],
) -> None:
    """Shallow-merge ``attrs`` into news_articles.attrs."""
    if not attrs:
        return
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE news_articles
                SET attrs = COALESCE(attrs, '{}'::jsonb) || %s::jsonb
                WHERE id = %s
                """,
                (_json(attrs), str(article_id)),
            )
        conn.commit()


def mark_body_fetched(
    article_id: UUID | str,
    *,
    body_text: str,
    attrs: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    with connect() as conn:
        with conn.cursor() as cur:
            if attrs:
                cur.execute(
                    """
                    UPDATE news_articles
                    SET body_text = %s,
                        body_fetched_at = %s,
                        body_fetch_error = NULL,
                        attrs = COALESCE(attrs, '{}'::jsonb) || %s::jsonb
                    WHERE id = %s
                    """,
                    (body_text, now, _json(attrs), str(article_id)),
                )
            else:
                cur.execute(
                    """
                    UPDATE news_articles
                    SET body_text = %s,
                        body_fetched_at = %s,
                        body_fetch_error = NULL
                    WHERE id = %s
                    """,
                    (body_text, now, str(article_id)),
                )
        conn.commit()


def mark_body_failed(
    article_id: UUID | str,
    *,
    error: str,
) -> None:
    now = datetime.now(timezone.utc)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE news_articles
                SET body_fetch_error = %s,
                    body_fetched_at = %s
                WHERE id = %s
                """,
                ((error or "")[:2000], now, str(article_id)),
            )
        conn.commit()


def _json(value: dict[str, Any] | None) -> str:
    import json

    return json.dumps(value or {}, ensure_ascii=False)
