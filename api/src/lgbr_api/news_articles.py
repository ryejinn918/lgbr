"""Other-media lane: list news_articles (not FnGuide reports)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from lgbr_api.db import connect

# Phase 1 allowlist for the other-media document lane.
OTHER_MEDIA_SOURCES = frozenset({"arg"})


def list_articles(
    *,
    source: str | None = "all",
    q: str | None = None,
    limit: int = 30,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

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
        }

    q_s = (q or "").strip()
    if q_s:
        where.append("(title ILIKE %s OR url ILIKE %s OR publisher ILIKE %s)")
        like = f"%{q_s}%"
        params.extend([like, like, like])

    where_sql = " AND ".join(where)
    with connect() as conn:
        with conn.cursor() as cur:
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
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


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
    if isinstance(out.get("attrs"), dict):
        section = out["attrs"].get("section")
    out["section"] = section or out.get("publisher")
    body = out.get("body_text")
    out["has_body"] = bool(body and str(body).strip())
    return out
