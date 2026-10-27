"""Consensus worker: select reports → compress → frame → fill → DB outputs."""

from __future__ import annotations

import asyncio
import os
import traceback
from pathlib import Path
from typing import Any

from consensus import runs_store
from consensus.cite import (
    format_published_at,
    resolve_short_title,
    short_provider,
)
from consensus.compress import local_compress_all, report_compress
from consensus.corpus import (
    build_page_corpus,
    sha256_file,
    slices_from_toc,
    slug_from_report,
    write_corpus_artifacts,
)
from consensus.fill import fill_frame
from consensus.external_evidence import format_external_evidence, load_external_evidence
from consensus.evidence_policy import evidence_assessment
from consensus.frame import build_consensus
from consensus.llm import DEFAULT_MODEL, log
from consensus.paths import doc_cache_dir, make_asset_id, run_dir
from consensus.run_log import ConsensusLogger
from consensus.toc import probe_toc

# OpenRouter-bound I/O: parallelize docs and in-doc slices.
DOC_CONCURRENCY = 16
SLICE_CONCURRENCY = 4


class StopRequested(Exception):
    """Cooperative cancel when the operator requests stop."""


def _clip_msg(s: Any, n: int) -> str:
    t = " ".join(str(s or "").split())
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


def _ensure_not_stopped(run_id: str) -> None:
    if runs_store.is_stop_requested(run_id):
        raise StopRequested("stop requested")


def _selected_reports_from_run_docs(run_id: str) -> list[dict[str, Any]]:
    """Map persisted pack rows into the shape expected by _process_doc."""
    out: list[dict[str, Any]] = []
    for d in runs_store.list_selected_docs_for_refill(run_id):
        rid = str(d.get("report_id") or "").strip()
        fp = str(d.get("file_path") or "").strip()
        if not rid or not fp:
            continue
        out.append(
            {
                "id": rid,
                "source_key": str(d.get("source_key") or rid),
                "title": str(d.get("title") or ""),
                "provider": str(d.get("provider") or ""),
                "published_at": d.get("published_at"),
                "file_path": fp,
                "quality_json": d.get("quality_json"),
                "select_role": str(d.get("role") or "selected"),
            }
        )
    return out


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
    select_role = str(report.get("select_role") or "selected")
    pdf_path = Path(report["file_path"])
    if not pdf_path.is_file():
        raise FileNotFoundError(str(pdf_path))

    content_hash = sha256_file(pdf_path)
    cache = doc_cache_dir(report_id, content_hash)
    title = str(report.get("title") or "")
    provider = str(report.get("provider") or "").strip()
    slug = slug_from_report(
        source_key=str(report["source_key"]), title=title
    )
    cite_provider = short_provider(provider)
    cite_title = resolve_short_title(
        title,
        short_title=report.get("short_title"),
        quality_json=report.get("quality_json"),
    )
    cite_published = format_published_at(report.get("published_at"))

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
            select_role=select_role,
        )
        runs_store.update_run_doc(
            run_id,
            report_id,
            doc_status="cache_hit",
            artifact_id=existing["id"],
        )
        return {
            "slug": slug,
            "provider": cite_provider,
            "short_title": cite_title,
            "published_at": cite_published,
            "title": title,
            "source_pdf": str(pdf_path),
            "compress": existing["compress_md"],
            "cache_dir": cache,
            "report_id": report_id,
            "toc_found": existing.get("toc_found"),
            "slice_count": existing.get("slice_count"),
            "from_cache": True,
            "select_role": select_role,
        }

    log_c.emit(
        stage="doc",
        event="cache_miss",
        report_id=report_id,
        source_key=report["source_key"],
    )
    cache.mkdir(parents=True, exist_ok=True)
    page_corpus = await asyncio.to_thread(build_page_corpus, pdf_path)
    if page_corpus["corpus_char_len"] < 80:
        raise RuntimeError("empty or unreadable PDF text")

    toc = await probe_toc(page_corpus, window=8, model=model, out_dir=cache)
    slices, split_count = slices_from_toc(page_corpus, toc)
    write_corpus_artifacts(cache, page_corpus, slices)
    max_slice_chars = max((s.get("char_len") or 0) for s in slices) if slices else 0
    log_c.emit(
        stage="doc",
        event="toc_done",
        report_id=report_id,
        toc_found=bool(toc.get("toc_found")),
        slice_count=len(slices),
        max_slice_chars=max_slice_chars,
        split_count=split_count,
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
        "provider": cite_provider,
        "short_title": cite_title,
        "published_at": cite_published,
        "title": title,
        "corpus_char_len": page_corpus["corpus_char_len"],
    }
    compress_md = await report_compress(
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
        "provider": cite_provider,
        "short_title": cite_title,
        "published_at": cite_published,
        "title": title,
        "source_pdf": str(pdf_path),
        "compress": compress_md,
        "cache_dir": cache,
        "report_id": report_id,
        "toc_found": bool(toc.get("toc_found")),
        "slice_count": len(slices),
        "from_cache": False,
        "select_role": select_role,
    }


async def run_pipeline(run_id: str) -> None:
    pid = os.getpid()
    if runs_store.is_stop_requested(run_id):
        runs_store.end_run(
            run_id, state="ended", message="종료 요청으로 시작 전 종료됨"
        )
        log(f"STOPPED pre-claim run={run_id}")
        return
    row = runs_store.claim_run(run_id, pid=pid)
    if row is None:
        if runs_store.is_stop_requested(run_id):
            runs_store.end_run(
                run_id, state="ended", message="종료 요청으로 시작 전 종료됨"
            )
            log(f"STOPPED claim-blocked run={run_id}")
            return
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
    criteria0 = dict(row.get("criteria") or {})
    until = str(criteria0.get("until") or "").strip()
    resume_from = str(criteria0.get("resume_from") or "").strip()
    if resume_from == "doc":
        start_stage = "doc"
    elif resume_from == "select":
        start_stage = "select"
    else:
        start_stage = "thesis"
    log_c.set_progress(
        stage=start_stage,
        theme=theme,
        artifact_dir=str(out),
        model=model,
    )

    try:
        selected: list[dict[str, Any]]
        criteria: dict[str, Any]

        if resume_from == "doc":
            # Keep locked pack; skip select LLM; continue doc → frame → fill.
            _ensure_not_stopped(run_id)
            selected = _selected_reports_from_run_docs(run_id)
            if not selected:
                raise RuntimeError("resume_from=doc but no selected run_docs")
            criteria = dict(criteria0)
            criteria.pop("resume_from", None)
            criteria.pop("until", None)
            runs_store.set_run_criteria(run_id, criteria)
            core_n = sum(
                1 for r in selected if r.get("select_role") != "fill_extra"
            )
            biblio_n = sum(
                1 for r in selected if r.get("select_role") == "fill_extra"
            )
            log_c.emit(
                stage="doc",
                event="resume_pack",
                selected=len(selected),
                core=core_n,
                bibliography=biblio_n,
            )
            log_c.set_progress(
                docs_total=len(selected),
                docs_done=0,
                docs_failed=0,
                docs_cache_hit=0,
            )

        elif resume_from == "select":
            # Place reports on locked axes, then optional early end.
            _ensure_not_stopped(run_id)
            thesis = str(criteria0.get("thesis") or "").strip()
            cut_logic = str(criteria0.get("cut_logic") or "").strip()
            pillars = criteria0.get("pillar_sketch") or []
            if not isinstance(pillars, list):
                pillars = []

            with log_c.stage("select", theme=theme):
                from consensus.select import select_for_theme

                _ensure_not_stopped(run_id)
                selected, excluded_pairs, criteria = await select_for_theme(
                    theme,
                    thesis=thesis,
                    cut_logic=cut_logic,
                    pillar_sketch=[str(p) for p in pillars],
                    model=model,
                )
                if not selected:
                    raise RuntimeError(f"no reports selected for theme={theme}")

                core_n = sum(
                    1 for r in selected if r.get("select_role") != "fill_extra"
                )
                biblio_n = sum(
                    1 for r in selected if r.get("select_role") == "fill_extra"
                )
                for k in (
                    "thesis",
                    "cut_logic",
                    "pillar_sketch",
                    "cut",
                    "pool_qp_count",
                    "until",
                ):
                    if k in criteria0 and k not in criteria:
                        criteria[k] = criteria0[k]
                criteria["thesis"] = thesis
                criteria["cut_logic"] = cut_logic
                criteria["pillar_sketch"] = (
                    list(pillars) or criteria.get("pillar_sketch")
                )
                criteria.pop("resume_from", None)
                if until:
                    criteria["until"] = until

                runs_store.insert_run_docs(
                    run_id, selected=selected, excluded=excluded_pairs
                )
                runs_store.set_run_criteria(run_id, criteria)
                runs_store.update_progress(
                    run_id, {"criteria_snapshot": criteria}
                )
                log_c.emit(
                    stage="select",
                    event="selected",
                    selected=len(selected),
                    core=core_n,
                    bibliography=biblio_n,
                    excluded=len(excluded_pairs),
                    **{
                        k: criteria[k]
                        for k in (
                            "select",
                            "pool_themes",
                            "core_max",
                            "pillar_sketch",
                        )
                        if k in criteria
                    },
                )
                log_c.set_progress(
                    docs_total=len(selected),
                    docs_done=0,
                    docs_failed=0,
                    docs_cache_hit=0,
                )

            if until == "select":
                _ensure_not_stopped(run_id)
                msg = f"ok until=select core={core_n} biblio={biblio_n}"
                runs_store.end_run(run_id, state="ended", message=msg)
                log_c.emit(
                    stage="run",
                    event="ended",
                    until="select",
                    core=core_n,
                    bibliography=biblio_n,
                )
                log(f"DONE run={run_id} {msg}")
                return

        else:
            _ensure_not_stopped(run_id)
            with log_c.stage("thesis", theme=theme):
                from consensus.thesis import thesis_for_theme

                cut = await thesis_for_theme(theme, model=model)
                criteria = {**criteria0, **cut}
                criteria.pop("resume_from", None)
                thesis_progress = {
                    "stage": "thesis",
                    "criteria_snapshot": {
                        k: criteria.get(k)
                        for k in (
                            "thesis",
                            "cut_logic",
                            "pillar_sketch",
                            "pool_qp_count",
                        )
                    },
                }
                msg = "awaiting axis review"
                paused = runs_store.complete_thesis(
                    run_id,
                    criteria=criteria,
                    progress=thesis_progress,
                    message=msg,
                )
                log_c.emit(
                    stage="thesis",
                    event="cut_done",
                    pillars=len(criteria.get("pillar_sketch") or []),
                    thesis=_clip_msg(criteria.get("thesis"), 120),
                )
            if paused == "ended":
                log_c.emit(stage="run", event="ended", reason="stop_before_awaiting")
                log(f"STOPPED before awaiting run={run_id}")
                return
            log_c.emit(stage="run", event="awaiting", until="thesis")
            log(f"AWAITING run={run_id} {msg}")
            return

        _ensure_not_stopped(run_id)
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
                _ensure_not_stopped(run_id)
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

        _ensure_not_stopped(run_id)
        frame_cards = [
            c for c in cards if c.get("select_role") != "fill_extra"
        ]
        if not frame_cards:
            frame_cards = cards

        external_evidence = format_external_evidence(load_external_evidence(run_id))
        evidence_note = criteria.get("evidence_note") if criteria.get("evidence_notice") else None
        if not evidence_note:
            assessment = evidence_assessment(selected, theme=theme)
            evidence_note = assessment.get("report_note") if assessment.get("notice") else None

        with log_c.stage("consensus", reports=len(frame_cards)):
            frame = await build_consensus(
                frame_cards,
                question=question,
                out_dir=consensus_dir,
                model=model,
                thesis=str(criteria.get("thesis") or "") or None,
                cut_logic=str(criteria.get("cut_logic") or "") or None,
                pillar_sketch=list(criteria.get("pillar_sketch") or []),
                external_evidence=external_evidence,
                evidence_note=evidence_note,
            )
            runs_store.save_output(run_id, kind="consensus_frame", body_md=frame)
            log_c.emit(stage="consensus", event="frame_validated", chars=len(frame))

        _ensure_not_stopped(run_id)
        with log_c.stage("fill", reports=len(slug_dirs)):
            filled, plan_meta = await fill_frame(
                frame,
                slug_dirs,
                question=question,
                out_dir=consensus_dir,
                model=model,
                compress_cards=cards,
                external_evidence=external_evidence,
                evidence_note=evidence_note,
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
    except StopRequested:
        msg = "종료 요청으로 중단됨"
        log_c.emit(stage="run", event="ended", reason="stop")
        runs_store.end_run(run_id, state="ended", message=msg)
        log(f"STOPPED run={run_id}")
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
    until: str | None = None,
) -> str:
    """Create a run. Fresh runs always stop after thesis (awaiting)."""
    if theme not in runs_store.THEMES:
        raise ValueError(f"theme must be one of {sorted(runs_store.THEMES)}")
    if until is not None and until not in ("thesis", "select"):
        raise ValueError("until must be 'thesis', 'select', or omitted")
    q = question or runs_store.DEFAULT_QUESTION[theme]
    prompt_set_id = runs_store.ensure_prompt_set(
        label=runs_store.DOC_PROMPT_SET_LABEL,
        notes="prompts executed from consensus package code",
    )
    asset_id = make_asset_id(theme)
    criteria: dict[str, Any] = {
        "quality_pass": True,
        "theme": theme,
        "until": until or "thesis",
    }
    run_id = runs_store.create_run(
        asset_id=asset_id,
        prompt_set_id=prompt_set_id,
        theme=theme,
        question=q,
        criteria=criteria,
        model=model,
    )
    return run_id


def main_run(run_id: str) -> None:
    asyncio.run(run_pipeline(run_id))


async def _refill_run_async(run_id: str, *, model: str | None = None) -> dict[str, Any]:
    """Re-run fill only for an existing run (reuse frame + doc caches)."""
    run = runs_store.get_run(run_id)
    if not run:
        raise RuntimeError(f"run not found: {run_id}")
    frame_out = runs_store.get_output(run_id, "consensus_frame")
    frame = (frame_out or {}).get("body_md") or ""
    if not frame.strip():
        raise RuntimeError(f"run {run_id} has no consensus_frame")

    question = str(run.get("question") or "")
    use_model = model or str(run.get("model") or DEFAULT_MODEL)
    run_criteria = dict(run.get("criteria") or {})
    evidence_note = run_criteria.get("evidence_note") if run_criteria.get("evidence_notice") else None
    asset_id = str(run["asset_id"])
    consensus_dir = run_dir(asset_id) / "_consensus"
    consensus_dir.mkdir(parents=True, exist_ok=True)

    docs = runs_store.list_selected_docs_for_refill(run_id)
    if not docs:
        raise RuntimeError(f"run {run_id} has no selected docs")
    if not evidence_note:
        assessment = evidence_assessment(docs, theme=str(run.get("theme") or ""))
        evidence_note = assessment.get("report_note") if assessment.get("notice") else None
    cards: list[dict[str, Any]] = []
    slug_dirs: dict[str, Path] = {}
    for d in docs:
        pdf = Path(str(d.get("file_path") or ""))
        if not pdf.is_file():
            log(f"refill: skip missing pdf report_id={d.get('report_id')}")
            continue
        content_hash = str(d.get("content_hash") or "") or sha256_file(pdf)
        cache = doc_cache_dir(str(d["report_id"]), content_hash)
        if not (cache / "01_slices").is_dir():
            # Fallback: any hash dir under report
            parent = cache.parent
            alts = sorted(
                p for p in parent.iterdir() if p.is_dir() and (p / "01_slices").is_dir()
            ) if parent.is_dir() else []
            if not alts:
                log(f"refill: skip no slices report_id={d.get('report_id')}")
                continue
            cache = alts[0]
        title = str(d.get("title") or "")
        slug = slug_from_report(
            source_key=str(d.get("source_key") or ""),
            title=title,
        )
        compress = str(d.get("compress_md") or "")
        if not compress:
            compress_path = cache / "03_report_compress.md"
            if compress_path.is_file():
                compress = compress_path.read_text(encoding="utf-8")
        slug_dirs[slug] = cache
        cards.append(
            {
                "slug": slug,
                "provider": short_provider(str(d.get("provider") or "")),
                "short_title": resolve_short_title(
                    title, quality_json=d.get("quality_json")
                ),
                "published_at": format_published_at(d.get("published_at")),
                "title": title,
                "source_pdf": str(pdf),
                "compress": compress,
                "cache_dir": cache,
                "report_id": d["report_id"],
                "slice_count": d.get("slice_count"),
                "toc_found": d.get("toc_found"),
                "from_cache": True,
            }
        )

    if not slug_dirs:
        raise RuntimeError("refill: no usable doc caches")

    log_c = ConsensusLogger(run_id)
    log_c.emit(
        stage="fill",
        event="refill_start",
        reports=len(slug_dirs),
        model=use_model,
    )
    with log_c.stage("fill", reports=len(slug_dirs), refill=True):
        filled, plan_meta = await fill_frame(
            frame,
            slug_dirs,
            question=question,
            out_dir=consensus_dir,
            model=use_model,
            compress_cards=cards,
            evidence_note=evidence_note,
        )
        runs_store.save_output(
            run_id, kind="fill_plan", body_json=plan_meta, body_md=None
        )
        runs_store.save_output(run_id, kind="filled_frame", body_md=filled)
        log_c.emit(stage="fill", event="filled_done", chars=len(filled), refill=True)

    msg = f"refilled opens={plan_meta.get('opens_used')} filled_chars={len(filled)}"
    runs_store.touch_run_message(run_id, msg)
    log(f"REFILL DONE run={run_id} {msg}")
    return {"run_id": run_id, "filled_chars": len(filled), "plan_meta": plan_meta}


def refill_run(run_id: str, *, model: str | None = None) -> dict[str, Any]:
    return asyncio.run(_refill_run_async(run_id, model=model))
