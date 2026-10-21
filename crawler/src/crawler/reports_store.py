"""Persist report metadata from list sightings and downloads."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from crawler.asset_id import DOWNLOADS_ROOT
from crawler.db import connect

SOURCE_FNGUIDE = "fnguide"
SOURCE_PWC = "pwc"
_FILENAME_RPT = re.compile(r"^(\d+)-(\d+)-")

STATUS_LISTED = "listed"
STATUS_BLIND = "blind"
STATUS_DOWNLOADED = "downloaded"
STATUS_NO_DOWNLOAD = "no_download"
STATUS_FAILED = "failed"

VALID_STATUSES = frozenset(
    {
        STATUS_LISTED,
        STATUS_BLIND,
        STATUS_DOWNLOADED,
        STATUS_NO_DOWNLOAD,
        STATUS_FAILED,
    }
)

# Merge crawl attrs but protect classified themes; fill themes only when empty.
_ATTRS_MERGE_SQL = """
COALESCE(reports.attrs, '{}'::jsonb)
    || (EXCLUDED.attrs - 'themes')
|| CASE
    WHEN (
        NOT (COALESCE(reports.attrs, '{}'::jsonb) ? 'themes')
        OR jsonb_typeof(COALESCE(reports.attrs, '{}'::jsonb)->'themes')
            <> 'array'
        OR jsonb_array_length(
            COALESCE(reports.attrs, '{}'::jsonb)->'themes'
        ) = 0
    )
    AND EXCLUDED.attrs ? 'themes'
    AND jsonb_typeof(EXCLUDED.attrs->'themes') = 'array'
    AND jsonb_array_length(EXCLUDED.attrs->'themes') > 0
    THEN jsonb_build_object('themes', EXCLUDED.attrs->'themes')
    ELSE '{}'::jsonb
END
"""

def existing_keys(source: str = SOURCE_FNGUIDE) -> set[str]:
    """All known source_keys (listed or downloaded). Prefer downloaded_keys for skip."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT source_key FROM reports WHERE source = %s",
                (source,),
            )
            return {str(r["source_key"]) for r in cur.fetchall()}


def downloaded_keys(source: str = SOURCE_FNGUIDE) -> set[str]:
    """Keys whose recorded PDF still exists on this machine.

    A restored database can contain absolute paths from another workstation.
    Those rows must not suppress a repair download on the current machine.
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_key, file_path FROM reports
                WHERE source = %s AND file_path IS NOT NULL
                """,
                (source,),
            )
            return {
                str(r["source_key"])
                for r in cur.fetchall()
                if Path(str(r.get("file_path") or "")).is_file()
            }

def _download_roots(root: Path | None = None) -> list[Path]:
    if root is not None:
        return [root]
    return [DOWNLOADS_ROOT]


def disk_rpt_ids(*, root: Path | None = None) -> set[str]:
    out: set[str] = set()
    for base in _download_roots(root):
        if not base.is_dir():
            continue
        for path in base.rglob("*.pdf"):
            match = _FILENAME_RPT.match(path.name)
            if match:
                out.add(match.group(2))
    return out


def _parse_published_at(published_at: date | str | None) -> date | None:
    if isinstance(published_at, date) and not isinstance(published_at, datetime):
        return published_at
    if isinstance(published_at, str) and published_at.strip():
        try:
            return date.fromisoformat(published_at.strip()[:10])
        except ValueError:
            return None
    return None


def upsert_listed(
    *,
    source: str,
    source_key: str,
    title: str,
    status: str = STATUS_LISTED,
    crawl_id: UUID | str | None = None,
    author: str | None = None,
    published_at: date | str | None = None,
    page_count: int | None = None,
    attrs: dict[str, Any] | None = None,
) -> str:
    """Insert or refresh a list sighting. Never clears file_path/downloaded_at.

    Returns the resulting status.
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    if status == STATUS_DOWNLOADED:
        raise ValueError("use mark_downloaded for downloaded status")

    pub = _parse_published_at(published_at)
    attrs_json = json.dumps(attrs or {}, ensure_ascii=False)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO reports (
                    source, source_key, crawl_id, title, author, published_at,
                    page_count, status, attrs, first_seen_at, last_seen_at,
                    downloaded_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                    now(), now(), NULL
                )
                ON CONFLICT (source, source_key) DO UPDATE SET
                    crawl_id = COALESCE(EXCLUDED.crawl_id, reports.crawl_id),
                    title = CASE
                        WHEN reports.file_path IS NOT NULL
                             OR reports.status = 'downloaded'
                        THEN reports.title
                        ELSE EXCLUDED.title
                    END,
                    author = COALESCE(EXCLUDED.author, reports.author),
                    published_at = COALESCE(EXCLUDED.published_at, reports.published_at),
                    page_count = COALESCE(EXCLUDED.page_count, reports.page_count),
                    attrs = {_ATTRS_MERGE_SQL},
                    last_seen_at = now(),
                    status = CASE
                        WHEN reports.file_path IS NOT NULL
                             OR reports.status = 'downloaded'
                        THEN reports.status
                        ELSE EXCLUDED.status
                    END
                RETURNING status
                """,
                (
                    source,
                    source_key,
                    str(crawl_id) if crawl_id else None,
                    title,
                    author,
                    pub,
                    page_count,
                    status,
                    attrs_json,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return str(row["status"]) if row else status


def mark_downloaded(
    *,
    source: str,
    source_key: str,
    title: str,
    crawl_id: UUID | str | None = None,
    author: str | None = None,
    published_at: date | str | None = None,
    page_count: int | None = None,
    file_path: str | None = None,
    file_name: str | None = None,
    attrs: dict[str, Any] | None = None,
) -> bool:
    """Upsert a downloaded report (file present). Always sets status=downloaded."""
    pub = _parse_published_at(published_at)
    attrs_json = json.dumps(attrs or {}, ensure_ascii=False)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO reports (
                    source, source_key, crawl_id, title, author, published_at,
                    page_count, file_path, file_name, status, attrs,
                    first_seen_at, last_seen_at, downloaded_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, 'downloaded', %s::jsonb,
                    now(), now(), now()
                )
                ON CONFLICT (source, source_key) DO UPDATE SET
                    crawl_id = COALESCE(EXCLUDED.crawl_id, reports.crawl_id),
                    title = EXCLUDED.title,
                    author = COALESCE(EXCLUDED.author, reports.author),
                    published_at = COALESCE(EXCLUDED.published_at, reports.published_at),
                    page_count = COALESCE(EXCLUDED.page_count, reports.page_count),
                    file_path = COALESCE(EXCLUDED.file_path, reports.file_path),
                    file_name = COALESCE(EXCLUDED.file_name, reports.file_name),
                    status = 'downloaded',
                    attrs = {_ATTRS_MERGE_SQL},
                    last_seen_at = now(),
                    downloaded_at = COALESCE(reports.downloaded_at, now())
                RETURNING id
                """,
                (
                    source,
                    source_key,
                    str(crawl_id) if crawl_id else None,
                    title,
                    author,
                    pub,
                    page_count,
                    file_path,
                    file_name,
                    attrs_json,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return row is not None


def insert_downloaded(**kwargs: Any) -> bool:
    """Backward-compatible alias for mark_downloaded."""
    return mark_downloaded(**kwargs)


def mark_status(
    *,
    source: str,
    source_key: str,
    status: str,
    crawl_id: UUID | str | None = None,
    title: str | None = None,
    attrs: dict[str, Any] | None = None,
    clear_download: bool = False,
) -> bool:
    """Update status for an existing (or minimal) row.

    By default won't demote downloaded. Pass ``clear_download=True`` to force
    status and clear file_path / file_name / downloaded_at (e.g. empty page.pdf
    re-capture).
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    if status == STATUS_DOWNLOADED:
        raise ValueError("use mark_downloaded for downloaded status")

    title_s = (title or "").strip() or source_key
    attrs_json = json.dumps(attrs or {}, ensure_ascii=False)
    if clear_download:
        status_sql = "EXCLUDED.status"
        clear_sql = """
                    file_path = NULL,
                    file_name = NULL,
                    downloaded_at = NULL,
                    page_count = NULL,
        """
    else:
        status_sql = """CASE
                        WHEN reports.file_path IS NOT NULL
                             OR reports.status = 'downloaded'
                        THEN reports.status
                        ELSE EXCLUDED.status
                    END"""
        clear_sql = ""
    title_sql = (
        "title = EXCLUDED.title,"
        if (title or "").strip()
        else ""
    )
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO reports (
                    source, source_key, crawl_id, title, status, attrs,
                    first_seen_at, last_seen_at, downloaded_at
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, now(), now(), NULL)
                ON CONFLICT (source, source_key) DO UPDATE SET
                    crawl_id = COALESCE(EXCLUDED.crawl_id, reports.crawl_id),
                    {title_sql}
                    status = {status_sql},
                    {clear_sql}
                    attrs = {_ATTRS_MERGE_SQL},
                    last_seen_at = now()
                RETURNING id
                """,
                (
                    source,
                    source_key,
                    str(crawl_id) if crawl_id else None,
                    title_s,
                    status,
                    attrs_json,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return row is not None


def backfill_from_disk(*, root: Path | None = None) -> int:
    """Insert minimal rows for legacy PDFs named NN-rptId-....pdf."""
    known = downloaded_keys(SOURCE_FNGUIDE)
    inserted = 0
    for base in _download_roots(root):
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.pdf")):
            match = _FILENAME_RPT.match(path.name)
            if not match:
                continue
            rpt_id = match.group(2)
            if rpt_id in known:
                continue
            rest = path.name[match.end() :]
            title = re.sub(r"\.pdf$", "", rest, flags=re.I).strip("_- ") or rpt_id
            asset_id = path.parent.name if path.parent != base else None
            ok = mark_downloaded(
                source=SOURCE_FNGUIDE,
                source_key=rpt_id,
                title=title[:500],
                file_path=str(path),
                file_name=path.name,
                attrs={
                    "rpt_id": rpt_id,
                    "legacy": True,
                    **({"asset_id": asset_id} if asset_id else {}),
                },
            )
            if ok:
                known.add(rpt_id)
                inserted += 1
    return inserted
