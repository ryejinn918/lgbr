"""Persist Google News hits (reports-style) and serve short-TTL query cache."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from psycopg.types.json import Jsonb

from lgbr_api.db import connect

SOURCE_GOOGLE_NEWS = "google_news"
CACHE_TTL_HOURS = 12

_TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}

_RELATIVE_RE = re.compile(
    r"^(\d+)\s*(second|minute|hour|day|week|month|year)s?\s+ago$",
    re.I,
)
_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%d",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d %b %Y",
    "%m/%d/%Y",
)


def normalize_query(query: str) -> str:
    q = (query or "").strip().lower()
    q = re.sub(r"\s+", " ", q)
    return q


def normalize_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    kept = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_QUERY_KEYS
    ]
    query = urlencode(kept, doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def _parse_published_at(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    now = datetime.now(timezone.utc)
    rel = _RELATIVE_RE.match(text)
    if rel:
        n = int(rel.group(1))
        unit = rel.group(2).lower()
        delta = {
            "second": timedelta(seconds=n),
            "minute": timedelta(minutes=n),
            "hour": timedelta(hours=n),
            "day": timedelta(days=n),
            "week": timedelta(weeks=n),
            "month": timedelta(days=30 * n),
            "year": timedelta(days=365 * n),
        }.get(unit)
        return now - delta if delta else None
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def article_to_result(row: dict[str, Any]) -> dict[str, str]:
    pub = row.get("published_at")
    published = ""
    if isinstance(pub, datetime):
        published = pub.isoformat()
    elif pub:
        published = str(pub)
    return {
        "title": str(row.get("title") or ""),
        "link": str(row.get("url") or ""),
        "snippet": str(row.get("snippet") or ""),
        "publisher": str(row.get("publisher") or ""),
        "published_at": published,
    }


def get_cached_search(
    query: str, *, max_age_hours: int = CACHE_TTL_HOURS
) -> list[dict[str, str]] | None:
    qn = normalize_query(query)
    if not qn:
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, last_searched_at
            FROM news_search_queries
            WHERE query_norm = %s AND engine = %s
            """,
            (qn, SOURCE_GOOGLE_NEWS),
        )
        qrow = cur.fetchone()
        if not qrow:
            return None
        last = qrow["last_searched_at"]
        if last is None or last < cutoff:
            return None
        cur.execute(
            """
            SELECT a.title, a.snippet, a.url, a.publisher, a.published_at
            FROM news_search_hits h
            JOIN news_articles a ON a.id = h.article_id
            WHERE h.query_id = %s
            ORDER BY h.rank ASC, h.searched_at DESC
            """,
            (qrow["id"],),
        )
        rows = cur.fetchall()
    if not rows:
        return None
    return [article_to_result(dict(r)) for r in rows]


def upsert_search_results(
    query: str, items: list[dict[str, Any]], *, engine: str = SOURCE_GOOGLE_NEWS
) -> list[dict[str, str]]:
    """Upsert articles + query hits; return result dicts for the tool/UI."""
    q_raw = (query or "").strip()
    qn = normalize_query(q_raw)
    if not qn:
        return []

    now = datetime.now(timezone.utc)
    out: list[dict[str, str]] = []

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO news_search_queries (query_norm, query_raw, engine, last_searched_at, hit_count)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (query_norm) DO UPDATE SET
                query_raw = EXCLUDED.query_raw,
                engine = EXCLUDED.engine,
                last_searched_at = EXCLUDED.last_searched_at,
                hit_count = EXCLUDED.hit_count
            RETURNING id::text
            """,
            (qn, q_raw or qn, engine, now, len(items)),
        )
        query_id = cur.fetchone()["id"]

        # Replace hit set for this query.
        cur.execute("DELETE FROM news_search_hits WHERE query_id = %s::uuid", (query_id,))

        for rank, item in enumerate(items):
            url = str(item.get("link") or item.get("url") or "").strip()
            key = normalize_url(url)
            if not key:
                continue
            title = str(item.get("title") or "").strip() or key
            snippet = str(item.get("snippet") or "").strip() or None
            publisher = str(item.get("publisher") or item.get("source") or "").strip() or None
            published_at = _parse_published_at(
                item.get("published_at") or item.get("date")
            )
            attrs = {
                k: item.get(k)
                for k in ("position", "thumbnail", "date")
                if item.get(k) is not None
            }
            cur.execute(
                """
                INSERT INTO news_articles (
                    source, source_key, title, snippet, url, published_at,
                    publisher, first_seen_at, last_seen_at, attrs
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (source, source_key) DO UPDATE SET
                    title = EXCLUDED.title,
                    snippet = COALESCE(EXCLUDED.snippet, news_articles.snippet),
                    url = EXCLUDED.url,
                    published_at = COALESCE(EXCLUDED.published_at, news_articles.published_at),
                    publisher = COALESCE(EXCLUDED.publisher, news_articles.publisher),
                    last_seen_at = EXCLUDED.last_seen_at,
                    attrs = COALESCE(news_articles.attrs, '{}'::jsonb) || EXCLUDED.attrs
                RETURNING id::text, title, snippet, url, publisher, published_at
                """,
                (
                    SOURCE_GOOGLE_NEWS,
                    key,
                    title,
                    snippet,
                    url,
                    published_at,
                    publisher,
                    now,
                    now,
                    Jsonb(attrs),
                ),
            )
            row = dict(cur.fetchone())
            cur.execute(
                """
                INSERT INTO news_search_hits (query_id, article_id, rank, searched_at)
                VALUES (%s::uuid, %s::uuid, %s, %s)
                ON CONFLICT (query_id, article_id) DO UPDATE SET
                    rank = EXCLUDED.rank,
                    searched_at = EXCLUDED.searched_at
                """,
                (query_id, row["id"], rank, now),
            )
            out.append(article_to_result(row))

        conn.commit()

    return out
