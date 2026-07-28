"""Report catalog API for the monitor."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from starlette.responses import FileResponse, JSONResponse, Response

from lgbr_api.db import connect

VALID_STATUSES = frozenset(
    {"listed", "blind", "downloaded", "no_download", "failed"}
)
VALID_QUALITIES = frozenset({"pass", "fail", "pending", "unauditable"})
# Auditable pending: downloaded with a file path (matches quality_audit fetch_targets).
_PENDING_SQL = (
    "quality_pass IS NULL AND status = 'downloaded' AND file_path IS NOT NULL"
)
_UNAUDITABLE_SQL = (
    "quality_pass IS NULL AND NOT "
    "(status = 'downloaded' AND file_path IS NOT NULL)"
)
VALID_THEMES = frozenset(
    {
        "datacenter",
        "ai",
        "physical_ai",
        "appliance",
        "display",
        "automotive",
        "petrochemical",
    }
)
VALID_SORTS = frozenset({"published_at", "page_count", "last_seen_at"})
SORT_SQL = {
    "published_at": "published_at DESC NULLS LAST, id DESC",
    "page_count": "page_count DESC NULLS LAST, published_at DESC NULLS LAST, id DESC",
    "last_seen_at": "last_seen_at DESC NULLS LAST, id DESC",
}

# api/src/lgbr_api/reports.py → repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
DOWNLOADS_ROOT = (_REPO_ROOT / ".crawler" / "downloads").resolve()


def _safe_download_path(file_path: str) -> Path | None:
    try:
        path = Path(file_path).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    try:
        path.relative_to(DOWNLOADS_ROOT)
    except ValueError:
        return None
    if not path.is_file():
        return None
    return path


def _quality_label(row: dict[str, Any]) -> str:
    qp = row.get("quality_pass")
    if qp is True:
        return "pass"
    if qp is False:
        return "fail"
    status = str(row.get("status") or "listed")
    if status == "downloaded" and row.get("file_path"):
        return "pending"
    return "unauditable"


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    pub = row.get("published_at")
    attrs = row.get("attrs") or {}
    if not isinstance(attrs, dict):
        attrs = {}
    provider = attrs.get("provider")
    provider_s = str(provider).strip() if provider else None
    theme = attrs.get("theme")
    theme_s = str(theme).strip() if theme else None
    if theme_s not in VALID_THEMES:
        theme_s = None
    qp = row.get("quality_pass")
    quality = _quality_label(row)
    return {
        "id": str(row["id"]),
        "source_key": row.get("source_key"),
        "title": row.get("title"),
        "status": row.get("status") or "listed",
        "has_file": bool(row.get("file_path")),
        "file_name": row.get("file_name"),
        "last_seen_at": (
            row["last_seen_at"].isoformat() if row.get("last_seen_at") else None
        ),
        "downloaded_at": (
            row["downloaded_at"].isoformat() if row.get("downloaded_at") else None
        ),
        "published_at": pub.isoformat() if pub else None,
        "provider": provider_s or None,
        "theme": theme_s,
        "page_count": row.get("page_count"),
        "crawl_id": str(row["crawl_id"]) if row.get("crawl_id") else None,
        "quality": quality,
        "quality_pass": qp,
        "quality_scope": row.get("quality_scope"),
        "quality_confidence": row.get("quality_confidence"),
        "quality_at": (
            row["quality_at"].isoformat() if row.get("quality_at") else None
        ),
    }


def _theme_where(theme: str | None) -> tuple[str, list[Any]]:
    if not theme:
        return "", []
    return " WHERE attrs->>'theme' = %s", [theme]


def _status_counts(cur: Any, *, theme: str | None = None) -> dict[str, int]:
    where_sql, params = _theme_where(theme)
    cur.execute(
        f"""
        SELECT status, count(*)::int AS n
        FROM reports
        {where_sql}
        GROUP BY status
        """,
        params,
    )
    counts = {s: 0 for s in VALID_STATUSES}
    total = 0
    for row in cur.fetchall():
        status = str(row["status"] or "listed")
        n = int(row["n"])
        if status in counts:
            counts[status] = n
        total += n
    counts["all"] = total
    return counts


def _quality_counts(cur: Any, *, theme: str | None = None) -> dict[str, int]:
    where_sql, params = _theme_where(theme)
    cur.execute(
        f"""
        SELECT
          count(*) FILTER (WHERE quality_pass IS TRUE)::int AS pass,
          count(*) FILTER (WHERE quality_pass IS FALSE)::int AS fail,
          count(*) FILTER (WHERE {_PENDING_SQL})::int AS pending,
          count(*) FILTER (WHERE {_UNAUDITABLE_SQL})::int AS unauditable
        FROM reports
        {where_sql}
        """,
        params,
    )
    row = cur.fetchone() or {}
    return {
        "pass": int(row.get("pass") or 0),
        "fail": int(row.get("fail") or 0),
        "pending": int(row.get("pending") or 0),
        "unauditable": int(row.get("unauditable") or 0),
    }


def _theme_counts(cur: Any) -> dict[str, int]:
    cur.execute(
        """
        SELECT attrs->>'theme' AS theme, count(*)::int AS n
        FROM reports
        WHERE attrs->>'theme' IS NOT NULL
        GROUP BY attrs->>'theme'
        """
    )
    counts = {t: 0 for t in VALID_THEMES}
    total = 0
    for row in cur.fetchall():
        theme = str(row["theme"] or "")
        n = int(row["n"])
        if theme in counts:
            counts[theme] = n
        total += n
    counts["all"] = total
    return counts


def list_reports(
    *,
    status: str | None = None,
    quality: str | None = None,
    theme: str | None = None,
    q: str | None = None,
    crawl_id: str | None = None,
    sort: str | None = None,
    limit: int = 30,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    def _error(message: str, *, sort_key: str) -> dict[str, Any]:
        return {
            "ok": False,
            "message": message,
            "status": 400,
            "items": [],
            "total": 0,
            "counts": {},
            "quality_counts": {},
            "theme_counts": {},
            "limit": limit,
            "offset": offset,
            "sort": sort_key,
        }

    sort_key = (sort or "last_seen_at").strip() or "last_seen_at"
    if sort_key not in VALID_SORTS:
        return _error(f"invalid sort: {sort_key}", sort_key=sort_key)
    order_sql = SORT_SQL[sort_key]

    status_filter: str | None = None
    if status and status != "all":
        if status not in VALID_STATUSES:
            return _error(f"invalid status: {status}", sort_key=sort_key)
        status_filter = status

    quality_filter: str | None = None
    if quality and quality != "all":
        if quality not in VALID_QUALITIES:
            return _error(f"invalid quality: {quality}", sort_key=sort_key)
        quality_filter = quality

    theme_filter: str | None = None
    if theme and theme != "all":
        if theme not in VALID_THEMES:
            return _error(f"invalid theme: {theme}", sort_key=sort_key)
        theme_filter = theme

    crawl_uuid: str | None = None
    if crawl_id:
        try:
            crawl_uuid = str(UUID(crawl_id))
        except (TypeError, ValueError):
            return _error("invalid crawl_id", sort_key=sort_key)

    q_pat = f"%{q.strip()}%" if q and q.strip() else None

    where: list[str] = []
    params: list[Any] = []
    if status_filter:
        where.append("status = %s")
        params.append(status_filter)
    if quality_filter == "pass":
        where.append("quality_pass IS TRUE")
    elif quality_filter == "fail":
        where.append("quality_pass IS FALSE")
    elif quality_filter == "pending":
        where.append(_PENDING_SQL)
    elif quality_filter == "unauditable":
        where.append(_UNAUDITABLE_SQL)
    if theme_filter:
        where.append("attrs->>'theme' = %s")
        params.append(theme_filter)
    if crawl_uuid:
        where.append("crawl_id = %s")
        params.append(crawl_uuid)
    if q_pat:
        where.append(
            "(title ILIKE %s OR source_key ILIKE %s OR attrs->>'provider' ILIKE %s "
            "OR coalesce(quality_json->>'short_title', '') ILIKE %s)"
        )
        params.extend([q_pat, q_pat, q_pat, q_pat])

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    with connect() as conn:
        with conn.cursor() as cur:
            counts = _status_counts(cur, theme=theme_filter)
            quality_counts = _quality_counts(cur, theme=theme_filter)
            theme_counts = _theme_counts(cur)
            cur.execute(
                f"SELECT count(*)::int AS n FROM reports{where_sql}",
                params,
            )
            total = int(cur.fetchone()["n"])
            cur.execute(
                f"""
                SELECT id, source_key, title, status, file_path, file_name,
                       last_seen_at, downloaded_at, published_at, page_count,
                       crawl_id, attrs,
                       quality_pass, quality_scope, quality_confidence, quality_at
                FROM reports
                {where_sql}
                ORDER BY {order_sql}
                LIMIT %s OFFSET %s
                """,
                [*params, limit, offset],
            )
            items = [_serialize(r) for r in cur.fetchall()]

    return {
        "ok": True,
        "items": items,
        "total": total,
        "counts": counts,
        "quality_counts": quality_counts,
        "theme_counts": theme_counts,
        "limit": limit,
        "offset": offset,
        "sort": sort_key,
    }


def get_report(report_id: str) -> dict[str, Any]:
    try:
        rid = str(UUID(report_id))
    except (TypeError, ValueError):
        return {
            "ok": False,
            "status": 400,
            "message": "invalid report id",
            "report": None,
        }

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, source_key, title, status, file_path, file_name,
                       last_seen_at, downloaded_at, published_at, page_count,
                       crawl_id, attrs,
                       quality_pass, quality_scope, quality_confidence,
                       quality_at, quality_model, quality_json
                FROM reports
                WHERE id = %s
                """,
                (rid,),
            )
            row = cur.fetchone()

    if row is None:
        return {
            "ok": False,
            "status": 404,
            "message": "report not found",
            "report": None,
        }

    data = _serialize(dict(row))
    data["quality_model"] = row.get("quality_model")
    qj = row.get("quality_json")
    if isinstance(qj, dict):
        data["quality_json"] = qj
    elif qj is None:
        data["quality_json"] = {}
    else:
        data["quality_json"] = {"raw": qj}
    return {"ok": True, "report": data}


def get_report_file(report_id: str) -> Response:
    try:
        rid = str(UUID(report_id))
    except (TypeError, ValueError):
        return JSONResponse(
            {"ok": False, "message": "invalid report id"},
            status_code=400,
        )

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT file_path, file_name
                FROM reports
                WHERE id = %s
                """,
                (rid,),
            )
            row = cur.fetchone()

    if row is None:
        return JSONResponse(
            {"ok": False, "message": "report not found"},
            status_code=404,
        )

    raw_path = row.get("file_path")
    if not raw_path:
        return JSONResponse(
            {"ok": False, "message": "no file for report"},
            status_code=404,
        )

    path = _safe_download_path(str(raw_path))
    if path is None:
        return JSONResponse(
            {"ok": False, "message": "file missing or outside downloads root"},
            status_code=404,
        )

    name = (row.get("file_name") or path.name or "report.pdf").strip()
    return FileResponse(
        path,
        filename=name,
        media_type="application/pdf",
    )
