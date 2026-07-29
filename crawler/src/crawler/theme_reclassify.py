"""Reclassify report content themes only — never touch quality_* / short_title."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

import httpx
from psycopg.types.json import Jsonb

from crawler.db import connect
from crawler.quality_audit import (
    DEFAULT_CONCURRENCY,
    DEFAULT_MODEL,
    OPENROUTER_URL,
    AuditTarget,
    openrouter_api_key,
    prepare_targets,
)
from crawler.report_themes import REPORT_THEMES, THEME_LABEL_KO

VALID_THEMES = REPORT_THEMES
_THEME_IDS = ", ".join(sorted(VALID_THEMES))
_THEME_LABEL_LINES = "\n".join(
    f"- {tid}: {THEME_LABEL_KO.get(tid, tid)}" for tid in sorted(VALID_THEMES)
)

SYSTEM_PROMPT = f"""You classify sell-side / research PDF excerpts into content themes.

Respond with a single JSON object only (no markdown):
{{
  "themes": string[]
}}

themes:
- Zero or more ids from this allowlist only: {_THEME_IDS}
- Labels:
{_THEME_LABEL_LINES}
- Multi-label OK when the note clearly covers more than one (e.g. AI + datacenter).
- Prefer precise labels: pure AIDC/power/cooling → datacenter; model/LLM/AI chip → ai;
  rates/inflation/FX/growth → macroeconomy. Do not dump every sector.
- Empty array only when truly off-list / unreadable.

Do NOT judge quality pass/fail. Themes only.
"""


def fetch_reclassify_targets(
    *,
    limit: int | None = None,
    report_id: UUID | str | None = None,
    missing_themes_only: bool = False,
) -> list[dict[str, Any]]:
    where = [
        "status = 'downloaded'",
        "file_path IS NOT NULL",
    ]
    params: list[Any] = []
    if report_id is not None:
        rid = report_id if isinstance(report_id, UUID) else UUID(str(report_id))
        where.append("id = %s")
        params.append(rid)
    elif missing_themes_only:
        where.append(
            "("
            "NOT (attrs ? 'themes')"
            " OR jsonb_typeof(attrs->'themes') <> 'array'"
            " OR jsonb_array_length(attrs->'themes') = 0"
            ")"
        )
    where_sql = " AND ".join(where)
    sql = f"""
        SELECT id, source, source_key, title, file_path, attrs,
               quality_pass, quality_confidence, quality_scope,
               quality_at, quality_json
        FROM reports
        WHERE {where_sql}
        ORDER BY last_seen_at DESC NULLS LAST, id DESC
    """
    if limit is not None:
        sql += " LIMIT %s"
        params.append(max(1, int(limit)))
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


def normalize_themes(raw: dict[str, Any]) -> list[str]:
    themes_raw = raw.get("themes")
    themes: list[str] = []
    if isinstance(themes_raw, list):
        for item in themes_raw:
            s = str(item).strip()
            if s in VALID_THEMES:
                themes.append(s)
    elif isinstance(themes_raw, str) and themes_raw.strip() in VALID_THEMES:
        themes = [themes_raw.strip()]
    return themes


def save_themes_only(report_id: UUID, themes: list[str]) -> None:
    """Update attrs.themes only. Quality columns and quality_json stay untouched."""
    clean = [str(t) for t in themes if str(t) in VALID_THEMES]
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE reports
                SET attrs = COALESCE(attrs, '{}'::jsonb)
                        || jsonb_build_object('themes', %s::jsonb)
                WHERE id = %s
                """,
                [Jsonb(clean), report_id],
            )
        conn.commit()


def _quality_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    qj = row.get("quality_json")
    short_title = None
    if isinstance(qj, dict):
        short_title = qj.get("short_title")
    return {
        "quality_pass": row.get("quality_pass"),
        "quality_confidence": row.get("quality_confidence"),
        "quality_scope": row.get("quality_scope"),
        "quality_at": row.get("quality_at"),
        "short_title": short_title,
    }


async def _classify_themes_one(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    model: str,
    target: AuditTarget,
    semaphore: asyncio.Semaphore,
) -> list[str]:
    body = {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "provider": {"sort": "throughput"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Title: {target.title}\n\n"
                    f"Report text (extracted from early pages):\n{target.text}"
                ),
            },
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost/lgbr",
        "X-Title": "lgbr-theme-reclassify",
    }
    async with semaphore:
        resp = await client.post(OPENROUTER_URL, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
    content = data["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("model response is not a JSON object")
    return normalize_themes(parsed)


async def run_reclassify(
    *,
    limit: int | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    model: str = DEFAULT_MODEL,
    report_id: UUID | str | None = None,
    missing_themes_only: bool = False,
    dry_run: bool = False,
) -> dict[str, int]:
    rows = fetch_reclassify_targets(
        limit=limit,
        report_id=report_id,
        missing_themes_only=missing_themes_only,
    )
    before = {str(r["id"]): _quality_snapshot(r) for r in rows}
    print(
        f"candidates={len(rows)} missing_only={missing_themes_only} "
        f"dry_run={dry_run} concurrency={concurrency}"
    )
    targets, extract_failures = prepare_targets(rows)
    stats = {
        "ok": 0,
        "fail_api": 0,
        "fail_extract": len(extract_failures),
        "quality_drift": 0,
    }
    for rid, err in extract_failures:
        print(f"extract_skip {rid}: {err}")

    if not targets:
        return stats

    api_key = openrouter_api_key()
    sem = asyncio.Semaphore(max(1, concurrency))
    lock = asyncio.Lock()

    async with httpx.AsyncClient(timeout=120.0) as client:

        async def run_one(target: AuditTarget) -> None:
            try:
                themes = await _classify_themes_one(
                    client,
                    api_key=api_key,
                    model=model,
                    target=target,
                    semaphore=sem,
                )
                if not dry_run:
                    await asyncio.to_thread(save_themes_only, target.id, themes)
                with connect() as conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT quality_pass, quality_confidence, quality_scope,
                               quality_at, quality_json
                        FROM reports WHERE id = %s
                        """,
                        (target.id,),
                    )
                    after_row = cur.fetchone() or {}
                snap_before = before.get(str(target.id), {})
                snap_after = _quality_snapshot(after_row)
                drifted = (
                    snap_before.get("quality_pass") != snap_after.get("quality_pass")
                    or snap_before.get("quality_confidence")
                    != snap_after.get("quality_confidence")
                    or snap_before.get("quality_scope")
                    != snap_after.get("quality_scope")
                    or snap_before.get("short_title") != snap_after.get("short_title")
                )
                async with lock:
                    stats["ok"] += 1
                    if drifted:
                        stats["quality_drift"] += 1
                print(
                    f"ok themes={themes} drift={drifted} "
                    f"{target.source_key} {target.title[:50]}"
                )
            except Exception as exc:  # noqa: BLE001
                async with lock:
                    stats["fail_api"] += 1
                print(f"err {target.source_key}: {exc}")

        await asyncio.gather(*(run_one(t) for t in targets))

    return stats
