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


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    pub = row.get("published_at")
    attrs = row.get("attrs") or {}
    if not isinstance(attrs, dict):
        attrs = {}
    provider = attrs.get("provider")
    provider_s = str(provider).strip() if provider else None
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
        "page_count": row.get("page_count"),
        "crawl_id": str(row["crawl_id"]) if row.get("crawl_id") else None,
    }


def _status_counts(cur: Any) -> dict[str, int]:
    cur.execute(
        """
        SELECT status, count(*)::int AS n
        FROM reports
        GROUP BY status
        """
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


def list_reports(
    *,
    status: str | None = None,
    q: str | None = None,
    crawl_id: str | None = None,
    sort: str | None = None,
    limit: int = 30,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    sort_key = (sort or "last_seen_at").strip() or "last_seen_at"
    if sort_key not in VALID_SORTS:
        return {
            "ok": False,
            "message": f"invalid sort: {sort_key}",
            "status": 400,
            "items": [],
            "total": 0,
            "counts": {},
            "limit": limit,
            "offset": offset,
            "sort": sort_key,
        }
    order_sql = SORT_SQL[sort_key]

    status_filter: str | None = None
    if status and status != "all":
        if status not in VALID_STATUSES:
            return {
                "ok": False,
                "message": f"invalid status: {status}",
                "status": 400,
                "items": [],
                "total": 0,
                "counts": {},
                "limit": limit,
                "offset": offset,
                "sort": sort_key,
            }
        status_filter = status

    crawl_uuid: str | None = None
    if crawl_id:
        try:
            crawl_uuid = str(UUID(crawl_id))
        except (TypeError, ValueError):
            return {
                "ok": False,
                "message": "invalid crawl_id",
                "status": 400,
                "items": [],
                "total": 0,
                "counts": {},
                "limit": limit,
                "offset": offset,
                "sort": sort_key,
            }

    q_pat = f"%{q.strip()}%" if q and q.strip() else None

    where: list[str] = []
    params: list[Any] = []
    if status_filter:
        where.append("status = %s")
        params.append(status_filter)
    if crawl_uuid:
        where.append("crawl_id = %s")
        params.append(crawl_uuid)
    if q_pat:
        where.append(
            "(title ILIKE %s OR source_key ILIKE %s OR attrs->>'provider' ILIKE %s)"
        )
        params.extend([q_pat, q_pat, q_pat])

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    with connect() as conn:
        with conn.cursor() as cur:
            counts = _status_counts(cur)
            cur.execute(
                f"SELECT count(*)::int AS n FROM reports{where_sql}",
                params,
            )
            total = int(cur.fetchone()["n"])
            cur.execute(
                f"""
                SELECT id, source_key, title, status, file_path, file_name,
                       last_seen_at, downloaded_at, published_at, page_count,
                       crawl_id, attrs
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
        "limit": limit,
        "offset": offset,
        "sort": sort_key,
    }


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
