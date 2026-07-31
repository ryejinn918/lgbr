"""Report catalog API for the monitor."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from starlette.responses import FileResponse, JSONResponse, Response

from lgbr_api.db import connect

COVERAGE_WEEKS_DEFAULT = 13
COVERAGE_SOURCES: tuple[tuple[str, str], ...] = (
    ("fnguide", "FnGuide"),
    ("arg", "ARG"),
    ("pwc", "PwC"),
    ("accenture", "Accenture"),
    ("kpmg", "KPMG"),
    ("ey", "EY"),
    ("deloitte", "Deloitte"),
    ("hbrkorea", "HBR Korea"),
    ("bain", "Bain"),
)
_REPORT_COVERAGE_SOURCES = (
    "fnguide",
    "pwc",
    "accenture",
    "kpmg",
    "ey",
    "deloitte",
    "hbrkorea",
    "bain",
)


def _monday_on_or_before(d: date) -> date:
    return d - timedelta(days=d.weekday())


def coverage_by_week(weeks: int | None = None) -> dict[str, Any]:
    """Weekly published_at counts per media for the coverage grass plot."""
    n = weeks if weeks is not None else COVERAGE_WEEKS_DEFAULT
    if n < 1:
        n = COVERAGE_WEEKS_DEFAULT
    if n > 52:
        n = 52

    end_monday = _monday_on_or_before(date.today())
    start_monday = end_monday - timedelta(weeks=n - 1)
    week_starts = [start_monday + timedelta(weeks=i) for i in range(n)]
    week_keys = [w.isoformat() for w in week_starts]

    tallies: dict[str, dict[str, int]] = {
        sid: {wk: 0 for wk in week_keys} for sid, _ in COVERAGE_SOURCES
    }

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source,
                       date_trunc('week', published_at::timestamp)::date
                         AS week_start,
                       count(*)::int AS n
                FROM reports
                WHERE source = ANY(%s)
                  AND published_at IS NOT NULL
                  AND published_at >= %s
                  AND published_at < %s
                GROUP BY 1, 2
                """,
                (
                    list(_REPORT_COVERAGE_SOURCES),
                    start_monday,
                    end_monday + timedelta(weeks=1),
                ),
            )
            for row in cur.fetchall():
                sid = str(row["source"])
                wk = row["week_start"]
                if sid not in tallies or wk is None:
                    continue
                key = wk.isoformat() if hasattr(wk, "isoformat") else str(wk)
                if key in tallies[sid]:
                    tallies[sid][key] = int(row["n"])

            cur.execute(
                """
                SELECT date_trunc('week', published_at)::date AS week_start,
                       count(*)::int AS n
                FROM news_articles
                WHERE source = 'arg'
                  AND published_at IS NOT NULL
                  AND published_at >= %s
                  AND published_at < %s
                GROUP BY 1
                """,
                (
                    start_monday,
                    end_monday + timedelta(weeks=1),
                ),
            )
            for row in cur.fetchall():
                wk = row["week_start"]
                if wk is None:
                    continue
                key = wk.isoformat() if hasattr(wk, "isoformat") else str(wk)
                if key in tallies["arg"]:
                    tallies["arg"][key] = int(row["n"])

    return {
        "ok": True,
        "weeks": week_keys,
        "sources": [
            {
                "id": sid,
                "label": label,
                "counts": [tallies[sid][wk] for wk in week_keys],
            }
            for sid, label in COVERAGE_SOURCES
        ],
    }

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
        "ai",
        "datacenter",
        "macroeconomy",
        "physical_ai",
        "appliance",
        "display",
        "automotive",
        "petrochemical",
    }
)
THEME_OTHER = "other"
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


def _themes_from_attrs(attrs: dict[str, Any]) -> list[str]:
    raw = attrs.get("themes")
    out: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            s = str(item).strip()
            if s in VALID_THEMES:
                out.append(s)
    if out:
        return out
    legacy = attrs.get("theme")
    if legacy is not None:
        s = str(legacy).strip()
        if s in VALID_THEMES:
            return [s]
    crawl = attrs.get("crawl_profile")
    if crawl is not None:
        s = str(crawl).strip()
        if s in VALID_THEMES:
            return [s]
    return []


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    pub = row.get("published_at")
    attrs = row.get("attrs") or {}
    if not isinstance(attrs, dict):
        attrs = {}
    provider = attrs.get("provider")
    provider_s = str(provider).strip() if provider else None
    themes = _themes_from_attrs(attrs)
    theme_s = themes[0] if themes else None
    crawl_raw = attrs.get("crawl_profile")
    crawl_s = str(crawl_raw).strip() if crawl_raw else None
    if not crawl_s:
        crawl_s = None
    qp = row.get("quality_pass")
    quality = _quality_label(row)
    raw_url = attrs.get("url")
    url_s = str(raw_url).strip() if raw_url else ""
    public_url = url_s if url_s.startswith(("http://", "https://")) else None
    return {
        "id": str(row["id"]),
        "source": row.get("source"),
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
        "themes": themes,
        "crawl_profile": crawl_s,
        "url": public_url,
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


# themes[] membership; if empty, match legacy theme or crawl_profile.
_THEME_MEMBER_SQL = (
    "("
    "attrs->'themes' ? %s"
    " OR ("
    "  (NOT (attrs ? 'themes')"
    "   OR jsonb_typeof(attrs->'themes') <> 'array'"
    "   OR jsonb_array_length(attrs->'themes') = 0)"
    "  AND ("
    "    attrs->>'theme' = %s"
    "    OR attrs->>'crawl_profile' = %s"
    "  )"
    ")"
    ")"
)

# Has at least one allowlisted sector theme (themes[] / legacy / crawl_profile).
_HAS_VALID_THEME_SQL = (
    "("
    "COALESCE(attrs->'themes', '[]'::jsonb) ?| %s::text[]"
    " OR ("
    "  (NOT (attrs ? 'themes')"
    "   OR jsonb_typeof(attrs->'themes') <> 'array'"
    "   OR jsonb_array_length(attrs->'themes') = 0)"
    "  AND ("
    "    COALESCE(attrs->>'theme', '') = ANY(%s)"
    "    OR COALESCE(attrs->>'crawl_profile', '') = ANY(%s)"
    "  )"
    ")"
    ")"
)

_VALID_THEME_LIST = sorted(VALID_THEMES)


def _theme_clause(theme: str) -> tuple[str, list[Any]]:
    """Return (sql, params) for a theme filter including virtual 'other'."""
    if theme == THEME_OTHER:
        return f"(NOT {_HAS_VALID_THEME_SQL})", [
            _VALID_THEME_LIST,
            _VALID_THEME_LIST,
            _VALID_THEME_LIST,
        ]
    return _THEME_MEMBER_SQL, [theme, theme, theme]


def _list_where(
    *,
    source: str | None = None,
    theme: str | None = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if source:
        clauses.append("source = %s")
        params.append(source)
    if theme:
        sql, tparams = _theme_clause(theme)
        clauses.append(sql)
        params.extend(tparams)
    if not clauses:
        return "", []
    return " WHERE " + " AND ".join(clauses), params


def _status_counts(
    cur: Any, *, source: str | None = None, theme: str | None = None
) -> dict[str, int]:
    where_sql, params = _list_where(source=source, theme=theme)
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


def _quality_counts(
    cur: Any, *, source: str | None = None, theme: str | None = None
) -> dict[str, int]:
    where_sql, params = _list_where(source=source, theme=theme)
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


def _theme_counts(cur: Any, *, source: str | None = None) -> dict[str, int]:
    where_sql, params = _list_where(source=source)
    base = "FROM reports" + (where_sql or "")
    cur.execute(
        f"""
        WITH keyed AS (
          SELECT id, jsonb_array_elements_text(attrs->'themes') AS theme
          {base}
            {"AND" if where_sql else "WHERE"}
            attrs ? 'themes'
            AND jsonb_typeof(attrs->'themes') = 'array'
            AND jsonb_array_length(attrs->'themes') > 0
          UNION ALL
          SELECT id, COALESCE(
            NULLIF(attrs->>'theme', ''),
            NULLIF(attrs->>'crawl_profile', '')
          ) AS theme
          {base}
            {"AND" if where_sql else "WHERE"}
            (
              NOT (attrs ? 'themes')
              OR jsonb_typeof(attrs->'themes') <> 'array'
              OR jsonb_array_length(attrs->'themes') = 0
            )
            AND (
              (attrs->>'theme' IS NOT NULL AND attrs->>'theme' <> '')
              OR (
                attrs->>'crawl_profile' IS NOT NULL
                AND attrs->>'crawl_profile' <> ''
              )
            )
        )
        SELECT theme, count(*)::int AS n
        FROM keyed
        WHERE theme IS NOT NULL AND theme <> ''
        GROUP BY theme
        """,
        params + params,
    )
    counts = {t: 0 for t in VALID_THEMES}
    for row in cur.fetchall():
        theme = str(row["theme"] or "")
        n = int(row["n"])
        if theme in counts:
            counts[theme] = n
    cur.execute(
        f"""
        WITH keyed AS (
          SELECT id
          {base}
            {"AND" if where_sql else "WHERE"}
            attrs ? 'themes'
            AND jsonb_typeof(attrs->'themes') = 'array'
            AND jsonb_array_length(attrs->'themes') > 0
          UNION
          SELECT id
          {base}
            {"AND" if where_sql else "WHERE"}
            (
              NOT (attrs ? 'themes')
              OR jsonb_typeof(attrs->'themes') <> 'array'
              OR jsonb_array_length(attrs->'themes') = 0
            )
            AND (
              (attrs->>'theme' IS NOT NULL AND attrs->>'theme' <> '')
              OR (
                attrs->>'crawl_profile' IS NOT NULL
                AND attrs->>'crawl_profile' <> ''
              )
            )
        )
        SELECT count(*)::int AS n FROM keyed
        """,
        params + params,
    )
    row = cur.fetchone() or {}
    themed = int(row.get("n") or 0)
    cur.execute(
        f"""
        SELECT count(*)::int AS n
        FROM reports
        {where_sql or ""}
        {"AND" if where_sql else "WHERE"}
        NOT {_HAS_VALID_THEME_SQL}
        """,
        [*params, _VALID_THEME_LIST, _VALID_THEME_LIST, _VALID_THEME_LIST],
    )
    other_row = cur.fetchone() or {}
    other_n = int(other_row.get("n") or 0)
    counts[THEME_OTHER] = other_n
    counts["all"] = themed + other_n
    return counts


def list_reports(
    *,
    source: str | None = None,
    status: str | None = None,
    quality: str | None = None,
    theme: str | None = None,
    q: str | None = None,
    provider: str | None = None,
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
        if theme != THEME_OTHER and theme not in VALID_THEMES:
            return _error(f"invalid theme: {theme}", sort_key=sort_key)
        theme_filter = theme

    crawl_uuid: str | None = None
    if crawl_id:
        try:
            crawl_uuid = str(UUID(crawl_id))
        except (TypeError, ValueError):
            return _error("invalid crawl_id", sort_key=sort_key)

    q_pat = f"%{q.strip()}%" if q and q.strip() else None
    provider_pat = (
        f"%{provider.strip()}%" if provider and provider.strip() else None
    )

    where: list[str] = []
    params: list[Any] = []
    source_s = (source or "").strip().lower() or None
    if source_s in (None, "", "all"):
        source_s = None
    if source_s:
        where.append("source = %s")
        params.append(source_s)
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
        sql, tparams = _theme_clause(theme_filter)
        where.append(sql)
        params.extend(tparams)
    if crawl_uuid:
        where.append("crawl_id = %s")
        params.append(crawl_uuid)
    if provider_pat:
        where.append("attrs->>'provider' ILIKE %s")
        params.append(provider_pat)
    if q_pat:
        where.append(
            "(title ILIKE %s OR source_key ILIKE %s OR attrs->>'provider' ILIKE %s "
            "OR coalesce(quality_json->>'short_title', '') ILIKE %s)"
        )
        params.extend([q_pat, q_pat, q_pat, q_pat])

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    with connect() as conn:
        with conn.cursor() as cur:
            counts = _status_counts(
                cur, source=source_s, theme=theme_filter
            )
            quality_counts = _quality_counts(
                cur, source=source_s, theme=theme_filter
            )
            theme_counts = _theme_counts(cur, source=source_s)
            cur.execute(
                f"SELECT count(*)::int AS n FROM reports{where_sql}",
                params,
            )
            total = int(cur.fetchone()["n"])
            cur.execute(
                f"""
                SELECT id, source, source_key, title, status, file_path, file_name,
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
            items = [_serialize(dict(r)) for r in cur.fetchall()]

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
                SELECT id, source, source_key, title, status, file_path, file_name,
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


def lookup_report_file(report_id: str) -> dict[str, Any]:
    """Resolve on-disk PDF path for a report (no HTTP response).

    Returns ``ok`` plus ``path`` / ``file_name``, or ``message`` + ``status``.
    """
    try:
        rid = str(UUID(report_id))
    except (TypeError, ValueError):
        return {
            "ok": False,
            "message": "invalid report id",
            "status": 400,
            "path": None,
            "file_name": None,
        }

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
        return {
            "ok": False,
            "message": "report not found",
            "status": 404,
            "path": None,
            "file_name": None,
        }

    raw_path = row.get("file_path")
    if not raw_path:
        return {
            "ok": False,
            "message": "no file for report",
            "status": 404,
            "path": None,
            "file_name": None,
        }

    path = _safe_download_path(str(raw_path))
    if path is None:
        return {
            "ok": False,
            "message": "file missing or outside downloads root",
            "status": 404,
            "path": None,
            "file_name": None,
        }

    name = (row.get("file_name") or path.name or "report.pdf").strip()
    return {
        "ok": True,
        "status": 200,
        "path": path,
        "file_name": name,
        "message": None,
    }


def get_report_file(report_id: str) -> Response:
    looked = lookup_report_file(report_id)
    if not looked.get("ok"):
        return JSONResponse(
            {"ok": False, "message": looked.get("message") or "error"},
            status_code=int(looked.get("status") or 404),
        )
    path = looked["path"]
    assert isinstance(path, Path)
    return FileResponse(
        path,
        filename=str(looked.get("file_name") or path.name),
        media_type="application/pdf",
    )
