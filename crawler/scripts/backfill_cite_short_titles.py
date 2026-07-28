#!/usr/bin/env python3
"""One-shot: fill quality_json.short_title without re-running full audit."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crawler.quality_audit import (  # noqa: E402
    DEFAULT_CONCURRENCY,
    DEFAULT_MODEL,
    OPENROUTER_URL,
    AuditTarget,
    extract_pdf_text,
    openrouter_api_key,
)
from crawler.db import connect  # noqa: E402

SHORT_TITLE_SYSTEM = """You invent a short citation nickname for a sell-side research PDF.

Respond with a single JSON object only (no markdown):
{"short_title": string}

Rules for short_title:
- Korean preferred; English only for proper nouns / series names.
- About 8–22 characters. Not a sentence.
- No broker/provider name (that is attached separately as [KB, short_title]).
- Prefer series / period / core theme; do not paste the full original title.
- Never put rpt_id, UUID, file paths, or hashes.
"""


def _clip_short_title(raw: Any) -> str:
    t = " ".join(str(raw or "").split())
    if len(t) > 28:
        return t[:27].rstrip() + "…"
    return t


def fetch_missing_short_title(
    *,
    limit: int | None = None,
    theme: str | None = None,
) -> list[dict[str, Any]]:
    where = [
        "status = 'downloaded'",
        "file_path IS NOT NULL",
        "quality_at IS NOT NULL",
        "coalesce(quality_json->>'short_title', '') = ''",
    ]
    params: list[Any] = []
    if theme:
        where.append("attrs->>'theme' = %s")
        params.append(str(theme))
    where_sql = " AND ".join(where)
    sql = f"""
        SELECT id, source_key, title, file_path, quality_json
        FROM reports
        WHERE {where_sql}
        ORDER BY last_seen_at DESC NULLS LAST, id DESC
    """
    if limit is not None:
        sql += " LIMIT %s"
        params.append(max(1, int(limit)))
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def prepare_targets(
    rows: list[dict[str, Any]],
) -> tuple[list[tuple[AuditTarget, dict[str, Any]]], list[tuple[UUID, str]]]:
    ready: list[tuple[AuditTarget, dict[str, Any]]] = []
    failures: list[tuple[UUID, str]] = []
    for row in rows:
        rid = row["id"]
        if not isinstance(rid, UUID):
            rid = UUID(str(rid))
        raw_path = row.get("file_path")
        if not raw_path:
            failures.append((rid, "missing file_path"))
            continue
        path = Path(str(raw_path))
        try:
            text = extract_pdf_text(path)
        except Exception as exc:  # noqa: BLE001
            failures.append((rid, f"extract: {exc}"))
            continue
        if len(text.strip()) < 80:
            failures.append((rid, "extract: text too short"))
            continue
        qj = row.get("quality_json")
        if not isinstance(qj, dict):
            qj = {}
        target = AuditTarget(
            id=rid,
            source_key=str(row.get("source_key") or ""),
            title=str(row.get("title") or ""),
            file_path=path,
            text=text,
        )
        ready.append((target, qj))
    ready.sort(key=lambda x: x[0].text_len)
    return ready, failures


def save_short_title(report_id: UUID, *, quality_json: dict[str, Any], short_title: str) -> None:
    payload = dict(quality_json)
    payload["short_title"] = short_title
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE reports
            SET quality_json = %s
            WHERE id = %s
            """,
            [Jsonb(payload), report_id],
        )
        conn.commit()


async def _one(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    model: str,
    target: AuditTarget,
    quality_json: dict[str, Any],
    semaphore: asyncio.Semaphore,
) -> str:
    body = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "provider": {"sort": "throughput"},
        "messages": [
            {"role": "system", "content": SHORT_TITLE_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Title: {target.title}\n\n"
                    f"Report text (early pages):\n{target.text}"
                ),
            },
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost/lgbr",
        "X-Title": "lgbr-cite-short-title-backfill",
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
    short = _clip_short_title(parsed.get("short_title"))
    if not short:
        raise ValueError("empty short_title")
    await asyncio.to_thread(
        save_short_title, target.id, quality_json=quality_json, short_title=short
    )
    return short


async def run_backfill(
    *,
    limit: int | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    model: str = DEFAULT_MODEL,
    theme: str | None = None,
) -> dict[str, int]:
    rows = fetch_missing_short_title(limit=limit, theme=theme)
    print(f"candidates={len(rows)} theme={theme} concurrency={concurrency}")
    ready, extract_failures = prepare_targets(rows)
    print(f"ready={len(ready)} extract_fail={len(extract_failures)}")
    for rid, err in extract_failures:
        print(f"extract-fail {rid}: {err}")

    api_key = openrouter_api_key()
    sem = asyncio.Semaphore(max(1, concurrency))
    stats = {
        "candidates": len(rows),
        "ok": 0,
        "fail_api": 0,
        "extract_fail": len(extract_failures),
    }
    lock = asyncio.Lock()

    async with httpx.AsyncClient(timeout=120.0) as client:

        async def run_one(target: AuditTarget, qj: dict[str, Any]) -> None:
            try:
                short = await _one(
                    client,
                    api_key=api_key,
                    model=model,
                    target=target,
                    quality_json=qj,
                    semaphore=sem,
                )
                async with lock:
                    stats["ok"] += 1
                print(f"ok {target.source_key} → {short}")
            except Exception as exc:  # noqa: BLE001
                async with lock:
                    stats["fail_api"] += 1
                print(f"err {target.source_key}: {exc}")

        await asyncio.gather(*(run_one(t, qj) for t, qj in ready))

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--theme", default=None)
    args = parser.parse_args()
    stats = asyncio.run(
        run_backfill(
            limit=args.limit,
            concurrency=args.concurrency,
            model=args.model,
            theme=args.theme,
        )
    )
    print("DONE", stats)


if __name__ == "__main__":
    main()
