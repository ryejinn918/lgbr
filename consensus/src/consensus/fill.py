"""Fill locked consensus frame by reopening report slices."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from consensus.llm import DEFAULT_MODEL, chat, log, parse_json


def _keyword_hits(text: str, queries: list[str], window: int = 1600, max_hits: int = 6) -> str:
    if not queries:
        return text[: min(len(text), window * 2)]
    chunks: list[str] = []
    lowered = text.lower()
    for q in queries:
        q = (q or "").strip()
        if not q:
            continue
        idx = lowered.find(q.lower())
        if idx < 0:
            continue
        start = max(0, idx - window // 3)
        end = min(len(text), idx + len(q) + window * 2 // 3)
        chunks.append(f"[hit q={q} @char={idx}]\n{text[start:end]}")
        if len(chunks) >= max_hits:
            break
    if not chunks:
        return f"[no keyword hits] queries={queries}\n" + text[: min(len(text), window)]
    return "\n\n----\n\n".join(chunks)


def fill_frame(
    frame: str,
    slug_to_dir: dict[str, Path],
    *,
    question: str,
    out_dir: Path,
    model: str = DEFAULT_MODEL,
) -> tuple[str, dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    slug_list = sorted(slug_to_dir)
    plan_raw, _ = chat(
        [
            {
                "role": "system",
                "content": "Output JSON only. Plan body opens to fill frame slots.",
            },
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n\nConsensus frame:\n{frame}\n\n"
                    "To fill 'slots to fill later' and 'Body re-open priority', "
                    "choose keywords to search in each report slice.\n"
                    "Important: queries must be short proper nouns/keywords that may "
                    "appear verbatim in the body — no long phrases or full sentences.\n"
                    "JSON:\n"
                    '{"opens":[{"slug":"...","slice_id":"s01|front_matter|whole",'
                    '"queries":["RMAC","Atlas"],"slot":"pillar/slot name","why":"..."}]}\n'
                    f"slug candidates: {slug_list}\n"
                    "For each slug pick a plausible slice_id among "
                    "front_matter/s01/s02/whole; use whole if unsure.\n"
                    "Emit enough opens to cover the slots."
                ),
            },
        ],
        model=model,
        temperature=0.15,
        label="fill_plan",
        out_dir=out_dir,
    )
    plan = parse_json(plan_raw)
    opens = plan.get("opens") or []
    log(f"fill: opens={len(opens)}")

    dossiers: list[dict[str, Any]] = []
    for i, op in enumerate(opens, 1):
        slug = (op.get("slug") or "").strip()
        slice_id = (op.get("slice_id") or "whole").strip()
        queries = op.get("queries") or []
        doc_dir = slug_to_dir.get(slug)
        if doc_dir is None:
            for k, d in slug_to_dir.items():
                if slug and (slug in k or k in slug):
                    doc_dir = d
                    slug = k
                    break
        if doc_dir is None:
            log(f"  skip open {i}: unknown slug={op.get('slug')}")
            continue

        slice_path = doc_dir / "01_slices" / f"{slice_id}.txt"
        if not slice_path.is_file():
            candidates = sorted((doc_dir / "01_slices").glob("*.txt"))
            if not candidates:
                log(f"  skip open {i}: no slices in {slug}")
                continue
            whole = doc_dir / "01_slices" / "whole.txt"
            slice_path = whole if whole.is_file() else candidates[0]
            slice_id = slice_path.stem
            log(f"  open {i}: slice fallback → {slice_id}")

        text = slice_path.read_text(encoding="utf-8")
        body = _keyword_hits(text, list(queries))
        hit_n = 0 if body.startswith("[no keyword hits]") else body.count("[hit ")
        log(f"  open [{i}] {slug}/{slice_id} queries={queries} hits={hit_n}")
        dossiers.append(
            {
                "slug": slug,
                "slice_id": slice_id,
                "slot": op.get("slot"),
                "why": op.get("why"),
                "queries": queries,
                "body": body,
                "hits": hit_n,
            }
        )
        (out_dir / f"05_open_{i}.txt").write_text(body, encoding="utf-8")

    usable = [d for d in dossiers if d["hits"] > 0 or d["body"]]
    if not usable:
        raise RuntimeError("fill: no body opens succeeded")

    with_hits = [d for d in usable if d["hits"] > 0]
    chosen = with_hits if with_hits else usable
    if not with_hits:
        log("fill: warning — no keyword hits; using slice excerpts")

    dossier_txt = "\n\n========\n\n".join(
        f"### OPEN {d['slug']}/{d['slice_id']} | slot={d['slot']} | why={d['why']}\n{d['body']}"
        for d in chosen
    )
    prompt = f"""Keep the locked consensus frame. Thicken pillars using **only**
sentences/numbers that actually appear in the OPEN excerpts below.
Do not rename roof/pillar titles.
Never invent numbers, company facts, or prices missing from OPEN; put gaps under empty slots.
Cite slug in evidence.

Question: {question}

## Locked frame
{frame}

## Opened body excerpts
{dossier_txt}

Output (English headers; Korean body OK for Korean sources):
# Filled frame (structure preserved)

## Roof
(same intent as locked frame)

## Pillar enrichment
### 1. (existing pillar title)
- **Claim**
- **Evidence (number / date / slug)**
- **Watch**
(dense)

## Still-empty slots (defer to web/other sources)
- Only items not filled from literature. One follow-up query candidate each.

## Reference reports
...
"""
    content, _ = chat(
        [
            {
                "role": "system",
                "content": (
                    "Enrich a locked consensus frame with opened report bodies. "
                    "Keep roof/pillars. Grow density. No invented facts. "
                    "English headers; Korean body when sources are Korean."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        model=model,
        temperature=0.25,
        label="fill",
        out_dir=out_dir,
    )
    (out_dir / "06_filled_frame.md").write_text(content, encoding="utf-8")
    log("fill DONE")
    return content, {"plan": plan, "raw": plan_raw, "opens_used": len(chosen)}
