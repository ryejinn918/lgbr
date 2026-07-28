#!/usr/bin/env python3
"""Copy ok doc-compress artifacts from legacy prompt_sets into consensus-doc-v2.

Cache keys include prompt_set_id. Older runs used per-theme labels
(``{theme}-api-v1``) that changed every start; the stable label is
``DOC_PROMPT_SET_LABEL``. This backfill re-keys ready artifacts so new runs
can cache-hit without recompressing.

Only copies rows that already have on-disk ``01_slices`` (required for hit).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "consensus" / "src"), str(ROOT)]

from consensus.db import connect  # noqa: E402
from consensus.paths import doc_cache_dir  # noqa: E402
from consensus.runs_store import DOC_PROMPT_SET_LABEL, ensure_prompt_set  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Count candidates without writing",
    )
    args = ap.parse_args()

    target_ps = ensure_prompt_set(
        label=DOC_PROMPT_SET_LABEL,
        notes="SSOT=consensus package code; DB prompts are placeholders (not loaded)",
    )
    print(f"target label={DOC_PROMPT_SET_LABEL} id={target_ps}")

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.report_id::text AS report_id,
                   a.content_hash,
                   a.model,
                   a.compress_md,
                   a.toc_found,
                   a.slice_count,
                   a.meta,
                   a.prompt_set_id::text AS src_ps,
                   ps.label AS src_label,
                   a.updated_at
            FROM consensus_doc_artifacts a
            JOIN consensus_prompt_sets ps ON ps.id = a.prompt_set_id
            WHERE a.status = 'ok'
              AND coalesce(a.compress_md, '') <> ''
              AND a.prompt_set_id <> %s::uuid
              AND NOT EXISTS (
                SELECT 1 FROM consensus_doc_artifacts t
                WHERE t.report_id = a.report_id
                  AND t.content_hash = a.content_hash
                  AND t.prompt_set_id = %s::uuid
                  AND t.model = a.model
                  AND t.status = 'ok'
                  AND coalesce(t.compress_md, '') <> ''
              )
            ORDER BY a.report_id, a.content_hash, a.model, a.updated_at DESC
            """,
            (target_ps, target_ps),
        )
        rows = list(cur.fetchall())

    best: dict[tuple[str, str, str], dict] = {}
    for r in rows:
        key = (r["report_id"], r["content_hash"], r["model"])
        if key not in best:
            best[key] = dict(r)

    inserted = 0
    skipped_no_slices = 0
    for r in best.values():
        cache = doc_cache_dir(r["report_id"], r["content_hash"])
        if not (cache / "01_slices").is_dir():
            skipped_no_slices += 1
            continue
        if args.dry_run:
            inserted += 1
            continue
        meta = r.get("meta") or {}
        if isinstance(meta, str):
            meta = json.loads(meta)
        meta = dict(meta)
        meta["backfilled_from_prompt_set"] = r["src_ps"]
        meta["backfilled_from_label"] = r["src_label"]
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO consensus_doc_artifacts (
                    report_id, content_hash, prompt_set_id, model, status,
                    toc_found, slice_count, compress_md, meta, updated_at
                )
                VALUES (
                    %s::uuid, %s, %s::uuid, %s, 'ok', %s, %s, %s, %s::jsonb, now()
                )
                ON CONFLICT (report_id, content_hash, prompt_set_id, model)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    toc_found = EXCLUDED.toc_found,
                    slice_count = EXCLUDED.slice_count,
                    compress_md = EXCLUDED.compress_md,
                    meta = EXCLUDED.meta,
                    updated_at = now()
                """,
                (
                    r["report_id"],
                    r["content_hash"],
                    target_ps,
                    r["model"],
                    r["toc_found"],
                    r["slice_count"],
                    r["compress_md"],
                    json.dumps(meta, ensure_ascii=False),
                ),
            )
            conn.commit()
        inserted += 1

    verb = "would_insert" if args.dry_run else "inserted"
    print(
        f"candidates={len(best)} {verb}={inserted} "
        f"skipped_no_slices={skipped_no_slices}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
