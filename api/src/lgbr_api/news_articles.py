"""Other-media lane: list news_articles (not FnGuide reports)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from lgbr_api.db import connect

# Document-lane news sources (filter chips / list allowlist).
OTHER_MEDIA_SOURCES = frozenset({"arg", "google_news", "nikkei"})
VALID_BODY = frozenset({"all", "yes", "no"})


def _parse_published_bound(value: str | None) -> datetime | None | str:
    """Parse ISO date/datetime. Returns datetime, None if empty, or 'invalid'."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        if len(normalized) == 10 and normalized[4] == "-" and normalized[7] == "-":
            dt = datetime.strptime(normalized, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
        else:
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return "invalid"


def list_articles(
    *,
    source: str | None = "all",
    q: str | None = None,
    has_body: str | None = "all",
    published_from: str | None = None,
    published_to: str | None = None,
    limit: int = 30,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    pub_from = _parse_published_bound(published_from)
    if pub_from == "invalid":
        return {
            "ok": False,
            "status": 400,
            "message": "published_from must be an ISO date or datetime",
            "items": [],
            "total": 0,
            "body_counts": {},
            "source_counts": {},
        }
    pub_to = _parse_published_bound(published_to)
    if pub_to == "invalid":
        return {
            "ok": False,
            "status": 400,
            "message": "published_to must be an ISO date or datetime",
            "items": [],
            "total": 0,
            "body_counts": {},
            "source_counts": {},
        }

    source_s = (source or "all").strip().lower()
    where: list[str] = []
    params: list[Any] = []
    if source_s in ("", "all", "*"):
        where.append("source = ANY(%s)")
        params.append(sorted(OTHER_MEDIA_SOURCES))
        source_out: str | list[str] = "all"
    elif source_s in OTHER_MEDIA_SOURCES:
        where.append("source = %s")
        params.append(source_s)
        source_out = source_s
    else:
        return {
            "ok": False,
            "status": 400,
            "message": (
                "source must be 'all' or one of: "
                + ", ".join(sorted(OTHER_MEDIA_SOURCES))
            ),
            "items": [],
            "total": 0,
            "body_counts": {},
            "source_counts": {},
        }

    q_s = (q or "").strip()
    if q_s:
        where.append("(title ILIKE %s OR url ILIKE %s OR publisher ILIKE %s)")
        like = f"%{q_s}%"
        params.extend([like, like, like])

    if isinstance(pub_from, datetime):
        where.append("published_at >= %s")
        params.append(pub_from)
    if isinstance(pub_to, datetime):
        where.append("published_at < %s")
        params.append(pub_to)

    body_s = (has_body or "all").strip().lower()
    if body_s not in VALID_BODY:
        return {
            "ok": False,
            "status": 400,
            "message": "has_body must be all, yes, or no",
            "items": [],
            "total": 0,
            "body_counts": {},
            "source_counts": {},
        }

    # Body / per-source chip counts ignore the active body & source filters
    # (same pattern as report status chips) but keep q and published_* bounds.
    base_where = ["source = ANY(%s)"]
    base_params: list[Any] = [sorted(OTHER_MEDIA_SOURCES)]
    if q_s:
        base_where.append(
            "(title ILIKE %s OR url ILIKE %s OR publisher ILIKE %s)"
        )
        like = f"%{q_s}%"
        base_params.extend([like, like, like])
    if isinstance(pub_from, datetime):
        base_where.append("published_at >= %s")
        base_params.append(pub_from)
    if isinstance(pub_to, datetime):
        base_where.append("published_at < %s")
        base_params.append(pub_to)
    base_where_sql = " AND ".join(base_where)

    # Counts for the selected source (or all) ignore body filter only.
    count_where_sql = " AND ".join(where)
    count_params = list(params)

    if body_s == "yes":
        where.append(
            "(body_text IS NOT NULL AND BTRIM(body_text) <> '')"
        )
    elif body_s == "no":
        where.append(
            "(body_text IS NULL OR BTRIM(body_text) = '')"
        )

    where_sql = " AND ".join(where)
    with connect() as conn:
        with conn.cursor() as cur:
            body_counts = _body_counts(cur, count_where_sql, count_params)
            source_counts = _source_counts(cur, base_where_sql, base_params)
            cur.execute(
                f"SELECT COUNT(*) AS n FROM news_articles WHERE {where_sql}",
                params,
            )
            total = int(cur.fetchone()["n"])
            cur.execute(
                f"""
                SELECT
                    id, source, source_key, title, snippet, url,
                    published_at, publisher, first_seen_at, last_seen_at, attrs,
                    body_text, body_fetched_at, body_fetch_error
                FROM news_articles
                WHERE {where_sql}
                ORDER BY
                    published_at DESC NULLS LAST,
                    last_seen_at DESC
                LIMIT %s OFFSET %s
                """,
                [*params, limit, offset],
            )
            items = [_serialize(dict(r)) for r in cur.fetchall()]

    return {
        "ok": True,
        "status": 200,
        "source": source_out,
        "has_body": body_s,
        "published_from": pub_from.isoformat() if isinstance(pub_from, datetime) else None,
        "published_to": pub_to.isoformat() if isinstance(pub_to, datetime) else None,
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "body_counts": body_counts,
        "source_counts": source_counts,
    }


def _body_counts(
    cur: Any, where_sql: str, params: list[Any]
) -> dict[str, int]:
    cur.execute(
        f"""
        SELECT
            COUNT(*)::int AS total,
            COUNT(*) FILTER (
                WHERE body_text IS NOT NULL AND BTRIM(body_text) <> ''
            )::int AS yes,
            COUNT(*) FILTER (
                WHERE body_text IS NULL OR BTRIM(body_text) = ''
            )::int AS no
        FROM news_articles
        WHERE {where_sql}
        """,
        params,
    )
    row = dict(cur.fetchone())
    return {
        "all": int(row.get("total") or 0),
        "yes": int(row.get("yes") or 0),
        "no": int(row.get("no") or 0),
    }


def _source_counts(
    cur: Any, where_sql: str, params: list[Any]
) -> dict[str, int]:
    """Per-source totals for filter chips (+ ``all``)."""
    cur.execute(
        f"""
        SELECT source, COUNT(*)::int AS n
        FROM news_articles
        WHERE {where_sql}
        GROUP BY source
        """,
        params,
    )
    by_source = {str(r["source"]): int(r["n"]) for r in cur.fetchall()}
    out: dict[str, int] = {"all": 0}
    for src in sorted(OTHER_MEDIA_SOURCES):
        n = int(by_source.get(src) or 0)
        out[src] = n
        out["all"] += n
    return out


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            out[key] = value.isoformat()
        elif isinstance(value, UUID):
            out[key] = str(value)
        else:
            out[key] = value
    attrs = out.get("attrs")
    if isinstance(attrs, str):
        try:
            out["attrs"] = json.loads(attrs)
        except Exception:
            out["attrs"] = {}
    elif attrs is None:
        out["attrs"] = {}
    section = None
    title_ko = None
    attrs_obj = out.get("attrs")
    if isinstance(attrs_obj, dict):
        section = attrs_obj.get("section")
        raw_ko = attrs_obj.get("title_ko")
        if raw_ko is not None and str(raw_ko).strip():
            title_ko = str(raw_ko).strip()
    out["section"] = section or out.get("publisher")
    out["title_ko"] = title_ko
    body = out.get("body_text")
    out["has_body"] = bool(body and str(body).strip())
    return out
