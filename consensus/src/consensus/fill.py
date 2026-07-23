"""Fill locked consensus frame by reopening report slices."""

from __future__ import annotations

import json
import re
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


def _slice_inventory(doc_dir: Path) -> list[str]:
    inv = doc_dir / "01_inventory.json"
    if inv.is_file():
        try:
            data = json.loads(inv.read_text(encoding="utf-8"))
            ids = [
                str(s.get("slice_id"))
                for s in (data.get("slices") or [])
                if s.get("slice_id")
            ]
            if ids:
                return ids
        except (json.JSONDecodeError, OSError):
            pass
    return sorted(p.stem for p in (doc_dir / "01_slices").glob("*.txt"))


def _extract_reopen_section(compress_md: str) -> str:
    """Pull the re-open candidates section from a report compress view."""
    text = compress_md or ""
    patterns = (
        r"(?im)^##\s*.*(?:re-?open|본문을 더 열|Candidates to re-open).*$",
        r"(?im)^##\s*.*후보.*$",
    )
    for pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        start = m.start()
        nxt = re.search(r"(?m)^##\s+", text[m.end() :])
        end = m.end() + nxt.start() if nxt else len(text)
        section = text[start:end].strip()
        if len(section) > 40:
            return section[:4000]
    # Fallback: last ~2k of compress (re-open is usually near the end).
    return text[-2000:] if text else "(no compress)"


def _build_reopen_index(
    compress_cards: list[dict[str, Any]],
    slug_to_dir: dict[str, Path],
) -> tuple[str, dict[str, list[str]]]:
    """Return prompt block + slug→valid slice_ids map."""
    slug_slices: dict[str, list[str]] = {}
    blocks: list[str] = []
    for card in compress_cards:
        slug = str(card.get("slug") or "")
        if not slug:
            continue
        doc_dir = slug_to_dir.get(slug) or Path(str(card.get("cache_dir") or ""))
        ids = _slice_inventory(doc_dir) if doc_dir and doc_dir.is_dir() else []
        if not ids and card.get("slice_count"):
            ids = []
        slug_slices[slug] = ids
        reopen = _extract_reopen_section(str(card.get("compress") or ""))
        blocks.append(
            f"### INDEX slug={slug}\n"
            f"valid_slice_ids: {json.dumps(ids, ensure_ascii=False)}\n"
            f"{reopen}\n"
        )
    return "\n========\n".join(blocks), slug_slices


def _resolve_slug(slug: str, slug_to_dir: dict[str, Path]) -> tuple[str | None, Path | None]:
    if slug in slug_to_dir:
        return slug, slug_to_dir[slug]
    for k, d in slug_to_dir.items():
        if slug and (slug in k or k in slug):
            return k, d
    return None, None


def _coerce_slice_id(slice_id: str, valid: list[str]) -> str | None:
    if not valid:
        return None
    sid = (slice_id or "").strip()
    if sid in valid:
        return sid
    # Common mistake: plan emits whole when only s01.. exist.
    if sid == "whole" and "whole" not in valid:
        non_fm = [v for v in valid if v != "front_matter"]
        return non_fm[0] if non_fm else valid[0]
    # Prefix / fuzzy: s1 → s01
    if re.fullmatch(r"s\d+", sid):
        padded = f"s{int(sid[1:]):02d}"
        if padded in valid:
            return padded
    return valid[0]


def fill_frame(
    frame: str,
    slug_to_dir: dict[str, Path],
    *,
    question: str,
    out_dir: Path,
    model: str = DEFAULT_MODEL,
    compress_cards: list[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cards = compress_cards or []
    reopen_index, slug_slices = _build_reopen_index(cards, slug_to_dir)
    if not reopen_index:
        # Minimal index from dirs only (cache-hit path without cards).
        parts = []
        for slug, doc_dir in sorted(slug_to_dir.items()):
            ids = _slice_inventory(doc_dir)
            slug_slices[slug] = ids
            parts.append(
                f"### INDEX slug={slug}\n"
                f"valid_slice_ids: {json.dumps(ids, ensure_ascii=False)}\n"
            )
        reopen_index = "\n========\n".join(parts)

    (out_dir / "05_reopen_index.md").write_text(reopen_index, encoding="utf-8")

    plan_raw, _ = chat(
        [
            {
                "role": "system",
                "content": (
                    "Output JSON only. Plan body opens to fill frame slots. "
                    "Use ONLY slugs and slice_ids listed in the reopen index. "
                    "Prefer short verbatim keywords from the index candidates."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n\n"
                    f"Consensus frame:\n{frame}\n\n"
                    "Reopen index (from report compress + real slice inventory).\n"
                    "Rules:\n"
                    "- slice_id MUST be one of that slug's valid_slice_ids "
                    "(never invent whole/s05 if absent).\n"
                    "- queries: 1–4 short tokens that may appear verbatim in the PDF "
                    "body (proper nouns, tickers, numbers). Prefer keywords already "
                    "listed in the index candidates. No long phrases.\n"
                    "- Cover frame slots / body re-open priority.\n"
                    "JSON:\n"
                    '{"opens":[{"slug":"...","slice_id":"s01",'
                    '"queries":["H54GV","684MW"],"slot":"pillar/slot","why":"..."}]}\n\n'
                    f"## Reopen index\n{reopen_index}"
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
        raw_slug = (op.get("slug") or "").strip()
        slug, doc_dir = _resolve_slug(raw_slug, slug_to_dir)
        if doc_dir is None or slug is None:
            log(f"  skip open {i}: unknown slug={op.get('slug')}")
            continue

        valid = slug_slices.get(slug) or _slice_inventory(doc_dir)
        coerced = _coerce_slice_id(str(op.get("slice_id") or ""), valid)
        if not coerced:
            log(f"  skip open {i}: no slices in {slug}")
            continue
        if coerced != (op.get("slice_id") or "").strip():
            log(
                f"  open {i}: slice coerce "
                f"{op.get('slice_id')!r} → {coerced!r} valid={valid}"
            )

        slice_path = doc_dir / "01_slices" / f"{coerced}.txt"
        if not slice_path.is_file():
            candidates = sorted((doc_dir / "01_slices").glob("*.txt"))
            if not candidates:
                log(f"  skip open {i}: missing file {slug}/{coerced}")
                continue
            slice_path = candidates[0]
            coerced = slice_path.stem
            log(f"  open {i}: slice file fallback → {coerced}")

        queries = [str(q).strip() for q in (op.get("queries") or []) if str(q).strip()]
        # Drop long phrase queries (>40 chars) — they almost never hit verbatim.
        short_q = [q for q in queries if len(q) <= 40]
        if not short_q and queries:
            # Keep first token-ish chunks from long phrases.
            for q in queries:
                for part in re.split(r"[\s,/|]+", q):
                    part = part.strip()
                    if 2 <= len(part) <= 40:
                        short_q.append(part)
                if len(short_q) >= 4:
                    break
        queries = short_q[:6] or queries[:3]

        text = slice_path.read_text(encoding="utf-8")
        body = _keyword_hits(text, list(queries))
        hit_n = 0 if body.startswith("[no keyword hits]") else body.count("[hit ")
        log(f"  open [{i}] {slug}/{coerced} queries={queries} hits={hit_n}")
        dossiers.append(
            {
                "slug": slug,
                "slice_id": coerced,
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
    return content, {
        "plan": plan,
        "raw": plan_raw,
        "opens_used": len(chosen),
        "opens_with_hits": len(with_hits),
        "slug_slices": slug_slices,
    }
