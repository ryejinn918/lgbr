"""Consensus worker: select reports → compress → frame → fill → DB outputs."""

from __future__ import annotations

import asyncio
import os
import traceback
from pathlib import Path
from typing import Any

from consensus import runs_store
from consensus.compress import local_compress_all, report_compress
from consensus.corpus import (
    build_page_corpus,
    sha256_file,
    slices_from_toc,
    slug_from_report,
    write_corpus_artifacts,
)
from consensus.fill import fill_frame
from consensus.frame import build_consensus
from consensus.llm import DEFAULT_MODEL, log
from consensus.paths import doc_cache_dir, make_asset_id, run_dir
from consensus.run_log import ConsensusLogger
from consensus.toc import probe_toc

# OpenRouter-bound I/O: parallelize docs and in-doc slices.
DOC_CONCURRENCY = 4
SLICE_CONCURRENCY = 4


async def _process_doc(
    report: dict[str, Any],
    *,
    run_id: str,
    prompt_set_id: str,
    question: str,
    model: str,
    log_c: ConsensusLogger,
) -> dict[str, Any]:
    report_id = str(report["id"])
    pdf_path = Path(report["file_path"])
    if not pdf_path.is_file():
        raise FileNotFoundError(str(pdf_path))

    content_hash = sha256_file(pdf_path)
    cache = doc_cache_dir(report_id, content_hash)
    slug = slug_from_report(
        source_key=str(report["source_key"]), title=str(report.get("title") or "")
    )

    existing = runs_store.find_artifact(
        report_id=report_id,
        content_hash=content_hash,
        prompt_set_id=prompt_set_id,
        model=model,
    )
    if existing and existing.get("compress_md") and (cache / "01_slices").is_dir():
        log_c.emit(
            stage="doc",
            event="cache_hit",
            report_id=report_id,
            source_key=report["source_key"],
        )
        runs_store.update_run_doc(
            run_id,
            report_id,
            doc_status="cache_hit",
            artifact_id=existing["id"],
        )
        return {
            "slug": slug,
            "source_pdf": str(pdf_path),
            "compress": existing["compress_md"],
            "cache_dir": cache,
            "report_id": report_id,
            "toc_found": existing.get("toc_found"),
            "slice_count": existing.get("slice_count"),
            "from_cache": True,
        }

    log_c.emit(
        stage="doc",
        event="cache_miss",
        report_id=report_id,
        source_key=report["source_key"],
    )
    cache.mkdir(parents=True, exist_ok=True)
    page_corpus = build_page_corpus(pdf_path)
    if page_corpus["corpus_char_len"] < 80:
        raise RuntimeError("empty or unreadable PDF text")

    toc = probe_toc(page_corpus, window=8, model=model, out_dir=cache)
    slices = slices_from_toc(page_corpus, toc)
    write_corpus_artifacts(cache, page_corpus, slices)
    log_c.emit(
        stage="doc",
        event="toc_done",
        report_id=report_id,
        toc_found=bool(toc.get("toc_found")),
        slice_count=len(slices),
    )

    cards = await local_compress_all(
        slices,
        question=question,
        out_dir=cache,
        model=model,
        concurrency=SLICE_CONCURRENCY,
    )
    meta = {
        "slug": slug,
        "source_pdf": str(pdf_path),
        "corpus_char_len": page_corpus["corpus_char_len"],
    }
    compress_md = report_compress(
        cards, meta, question=question, out_dir=cache, model=model
    )
    artifact_id = runs_store.upsert_artifact(
        report_id=report_id,
        content_hash=content_hash,
        prompt_set_id=prompt_set_id,
        model=model,
        status="ok",
        compress_md=compress_md,
        toc_found=bool(toc.get("toc_found")),
        slice_count=len(slices),
        meta={"slug": slug, "cache_dir": str(cache)},
    )
    runs_store.update_run_doc(
        run_id, report_id, doc_status="ok", artifact_id=artifact_id
    )
    log_c.emit(
        stage="doc",
        event="compress_done",
        report_id=report_id,
        chars=len(compress_md),
    )
    return {
        "slug": slug,
        "source_pdf": str(pdf_path),
        "compress": compress_md,
        "cache_dir": cache,
        "report_id": report_id,
        "toc_found": bool(toc.get("toc_found")),
        "slice_count": len(slices),
        "from_cache": False,
    }


async def run_pipeline(run_id: str) -> None:
    pid = os.getpid()
    row = runs_store.claim_run(run_id, pid=pid)
    if row is None:
        raise RuntimeError(f"cannot claim run {run_id}")

    log_c = ConsensusLogger(run_id)
    theme = row["theme"]
    question = row["question"]
    model = row["model"] or DEFAULT_MODEL
    prompt_set_id = row["prompt_set_id"]
    asset_id = row["asset_id"]
    out = run_dir(asset_id)
    out.mkdir(parents=True, exist_ok=True)
    consensus_dir = out / "_consensus"
    consensus_dir.mkdir(exist_ok=True)

    log_c.emit(stage="run", event="claimed", theme=theme, asset_id=asset_id, pid=pid)
    log_c.set_progress(
        stage="select", theme=theme, artifact_dir=str(out), model=model
    )

    try:
        with log_c.stage("select", theme=theme):
            all_docs = runs_store.list_theme_reports(theme)
            selected = [r for r in all_docs if r.get("quality_pass") is True]
            excluded_pairs = [
                (
                    r,
                    f"quality_pass={r.get('quality_pass')} scope={r.get('quality_scope')}",
                )
                for r in all_docs
                if r.get("quality_pass") is not True
            ]
            if not selected:
                raise RuntimeError(f"no quality_pass reports for theme={theme}")

            runs_store.insert_run_docs(
                run_id, selected=selected, excluded=excluded_pairs
            )
            criteria = {
                "quality_pass": True,
                "status": "downloaded",
                "theme": theme,
                "selected_count": len(selected),
                "excluded_count": len(excluded_pairs),
            }
            runs_store.update_progress(run_id, {"criteria_snapshot": criteria})
            from consensus.db import connect

            import json as _json

            with connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE consensus_runs SET criteria = %s::jsonb WHERE id = %s::uuid
                    """,
                    (_json.dumps(criteria, ensure_ascii=False), run_id),
                )
                conn.commit()
            log_c.emit(
                stage="select",
                event="selected",
                selected=len(selected),
                excluded=len(excluded_pairs),
            )
            log_c.set_progress(
                docs_total=len(selected), docs_done=0, docs_failed=0, docs_cache_hit=0
            )

        cards: list[dict[str, Any]] = []
        slug_dirs: dict[str, Path] = {}
        docs_done = docs_failed = docs_cache_hit = 0
        progress_lock = asyncio.Lock()
        doc_sem = asyncio.Semaphore(DOC_CONCURRENCY)

        async def _one_doc(
            index: int, report: dict[str, Any]
        ) -> tuple[int, dict[str, Any] | None]:
            nonlocal docs_done, docs_failed, docs_cache_hit
            rid = str(report["id"])
            async with doc_sem:
                log_c.set_progress(current_report_id=rid, stage="doc")
                try:
                    card = await _process_doc(
                        report,
                        run_id=run_id,
                        prompt_set_id=prompt_set_id,
                        question=question,
                        model=model,
                        log_c=log_c,
                    )
                    async with progress_lock:
                        docs_done += 1
                        if card.get("from_cache"):
                            docs_cache_hit += 1
                        log_c.set_progress(
                            docs_done=docs_done,
                            docs_failed=docs_failed,
                            docs_cache_hit=docs_cache_hit,
                        )
                    return index, card
                except Exception as exc:
                    async with progress_lock:
                        docs_failed += 1
                        log_c.set_progress(
                            docs_done=docs_done,
                            docs_failed=docs_failed,
                            docs_cache_hit=docs_cache_hit,
                        )
                    runs_store.update_run_doc(
                        run_id, rid, doc_status="failed", error=str(exc)
                    )
                    log_c.emit(
                        level="warn",
                        stage="doc",
                        event="doc_failed",
                        report_id=rid,
                        error=str(exc),
                    )
                    return index, None

        with log_c.stage(
            "doc",
            count=len(selected),
            doc_concurrency=DOC_CONCURRENCY,
            slice_concurrency=SLICE_CONCURRENCY,
        ):
            results = await asyncio.gather(
                *[_one_doc(i, r) for i, r in enumerate(selected)]
            )
            for _i, card in sorted(results, key=lambda x: x[0]):
                if card is None:
                    continue
                cards.append(card)
                slug_dirs[card["slug"]] = Path(card["cache_dir"])

        if not cards:
            raise RuntimeError("all documents failed compress")

        with log_c.stage("consensus", reports=len(cards)):
            frame = build_consensus(
                cards, question=question, out_dir=consensus_dir, model=model
            )
            runs_store.save_output(run_id, kind="consensus_frame", body_md=frame)
            log_c.emit(stage="consensus", event="frame_validated", chars=len(frame))

        with log_c.stage("fill", reports=len(slug_dirs)):
            filled, plan_meta = fill_frame(
                frame,
                slug_dirs,
                question=question,
                out_dir=consensus_dir,
                model=model,
                compress_cards=cards,
            )
            runs_store.save_output(
                run_id, kind="fill_plan", body_json=plan_meta, body_md=None
            )
            runs_store.save_output(run_id, kind="filled_frame", body_md=filled)
            log_c.emit(stage="fill", event="filled_done", chars=len(filled))

        runs_store.end_run(
            run_id,
            state="ended",
            message=f"ok docs={docs_done} failed={docs_failed} frame_chars={len(frame)}",
        )
        log_c.emit(stage="run", event="ended", docs_done=docs_done, docs_failed=docs_failed)
        log(f"DONE run={run_id} filled={len(filled)} chars")
    except Exception as exc:
        tb = traceback.format_exc()
        log_c.emit(level="error", stage="run", event="error", error=str(exc), traceback=tb)
        runs_store.end_run(run_id, state="error", message=str(exc)[:2000])
        raise


def start_theme_run(
    *,
    theme: str,
    question: str | None = None,
    model: str = DEFAULT_MODEL,
) -> str:
    if theme not in runs_store.THEMES:
        raise ValueError(f"theme must be one of {sorted(runs_store.THEMES)}")
    q = question or runs_store.DEFAULT_QUESTION[theme]
    prompt_set_id = runs_store.ensure_prompt_set(
        label=f"{theme}-runtime-v1",
        notes="prompts executed from consensus package code",
    )
    asset_id = make_asset_id(theme)
    run_id = runs_store.create_run(
        asset_id=asset_id,
        prompt_set_id=prompt_set_id,
        theme=theme,
        question=q,
        criteria={"quality_pass": True, "theme": theme},
        model=model,
    )
    return run_id


def main_run(run_id: str) -> None:
    asyncio.run(run_pipeline(run_id))
