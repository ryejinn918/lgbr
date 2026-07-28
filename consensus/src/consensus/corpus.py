"""PDF page corpus + TOC-based slicing."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pymupdf

# Cap for every slice fed to local_compress (TOC + mechanical).
SLICE_MAX_CHARS = 24_000


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def slug_from_report(*, source_key: str, title: str) -> str:
    head = re.sub(r"[^\w가-힣-]+", "", (title or source_key)[:40]) or source_key
    return f"{head[:24]}_{source_key}"


def build_page_corpus(pdf_path: Path) -> dict[str, Any]:
    doc = pymupdf.open(pdf_path)
    pages = []
    parts = []
    cursor = 0
    try:
        for i in range(doc.page_count):
            text = doc.load_page(i).get_text("text")
            marker = f"\n\n<<<PAGE {i + 1}>>>\n"
            block = marker + text
            start = cursor
            end = cursor + len(block)
            pages.append(
                {
                    "page": i + 1,
                    "char_start": start,
                    "char_end": end,
                    "char_len": len(block),
                    "text_sha256": sha256_text(block),
                }
            )
            parts.append(block)
            cursor = end
        corpus = "".join(parts)
        return {
            "source_pdf": str(pdf_path.resolve()),
            "total_pdf_pages": doc.page_count,
            "corpus_char_len": len(corpus),
            "corpus_sha256": sha256_text(corpus),
            "pages": pages,
            "corpus": corpus,
        }
    finally:
        doc.close()


def slice_from_pages(
    page_corpus: dict[str, Any], page_start: int, page_end: int
) -> dict[str, Any]:
    pages = {p["page"]: p for p in page_corpus["pages"]}
    if page_start not in pages or page_end not in pages:
        raise ValueError(f"bad page range {page_start}-{page_end}")
    if page_end < page_start:
        raise ValueError(f"bad page range {page_start}-{page_end}")
    char_start = pages[page_start]["char_start"]
    char_end = pages[page_end]["char_end"]
    text = page_corpus["corpus"][char_start:char_end]
    return {
        "page_start": page_start,
        "page_end": page_end,
        "char_start": char_start,
        "char_end": char_end,
        "char_len": len(text),
        "text_sha256": sha256_text(text),
        "text": text,
    }


def front_pages_text(page_corpus: dict[str, Any], window: int = 8) -> str:
    end = min(window, page_corpus["total_pdf_pages"])
    return slice_from_pages(page_corpus, 1, end)["text"]


def _slice_row(
    *,
    slice_id: str,
    title: str,
    source: str,
    sl: dict[str, Any],
) -> dict[str, Any]:
    return {
        "slice_id": slice_id,
        "title": title,
        "source": source,
        **{k: sl[k] for k in sl if k != "text"},
        "text": sl["text"],
    }


def split_oversized_by_pages(
    page_corpus: dict[str, Any],
    slice_row: dict[str, Any],
    *,
    max_chars: int = SLICE_MAX_CHARS,
    pages_per_slice: int = 4,
) -> list[dict[str, Any]]:
    """Partition one slice into page windows each ≤ max_chars (no content dropped)."""
    if slice_row["char_len"] <= max_chars:
        return [slice_row]

    page = int(slice_row["page_start"])
    end_limit = int(slice_row["page_end"])
    title = str(slice_row.get("title") or "")
    source = str(slice_row.get("source") or "toc")
    parts: list[dict[str, Any]] = []
    idx = 1
    while page <= end_limit:
        end = min(page + pages_per_slice - 1, end_limit)
        sl = slice_from_pages(page_corpus, page, end)
        while end > page and sl["char_len"] > max_chars:
            end -= 1
            sl = slice_from_pages(page_corpus, page, end)
        parts.append(
            _slice_row(
                slice_id=f"{slice_row['slice_id']}_{idx:02d}",
                title=title,
                source=source,
                sl=sl,
            )
        )
        idx += 1
        page = end + 1
    return parts


def _reindex_slices(slices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flat s01… ids; keep front_matter / whole as-is."""
    out: list[dict[str, Any]] = []
    n = 0
    for s in slices:
        sid = s.get("slice_id")
        if sid in ("front_matter", "whole"):
            out.append(s)
            continue
        n += 1
        out.append({**s, "slice_id": f"s{n:02d}"})
    return out


def enforce_slice_max(
    page_corpus: dict[str, Any],
    slices: list[dict[str, Any]],
    *,
    max_chars: int = SLICE_MAX_CHARS,
) -> tuple[list[dict[str, Any]], int]:
    """Split oversized slices by pages. Returns (slices, split_count).

    split_count = extra pieces created (len_after - len_before when positive).
    Renumbers to flat s01… only when at least one slice was split.
    """
    if not slices:
        return [], 0

    out: list[dict[str, Any]] = []
    did_split = False
    for s in slices:
        if s["char_len"] <= max_chars:
            out.append(s)
            continue
        parts = split_oversized_by_pages(
            page_corpus, s, max_chars=max_chars
        )
        if len(parts) > 1:
            did_split = True
        out.extend(parts)

    split_count = max(0, len(out) - len(slices))
    if did_split:
        out = _reindex_slices(out)
    return out, split_count


def mechanical_slices(
    page_corpus: dict[str, Any],
    *,
    pages_per_slice: int = 4,
    max_chars: int = SLICE_MAX_CHARS,
) -> list[dict[str, Any]]:
    """Page/char chunking when TOC is missing — keeps local_compress under truncate."""
    total = page_corpus["total_pdf_pages"]
    if total < 1:
        return []

    # Short docs: single whole slice is fine.
    full = slice_from_pages(page_corpus, 1, total)
    if total <= pages_per_slice and full["char_len"] <= max_chars:
        return [
            _slice_row(
                slice_id="whole",
                title="whole_document",
                source="mechanical_short",
                sl=full,
            )
        ]

    slices: list[dict[str, Any]] = []
    page = 1
    idx = 1
    while page <= total:
        end = min(page + pages_per_slice - 1, total)
        sl = slice_from_pages(page_corpus, page, end)
        while end > page and sl["char_len"] > max_chars:
            end -= 1
            sl = slice_from_pages(page_corpus, page, end)
        slices.append(
            _slice_row(
                slice_id=f"s{idx:02d}",
                title=f"pages_{page}-{end}",
                source="mechanical",
                sl=sl,
            )
        )
        idx += 1
        page = end + 1
    return slices


def _toc_range_list(toc: dict[str, Any]) -> list[dict[str, Any]]:
    ranges = toc.get("toc_ranges")
    if not isinstance(ranges, list) or not ranges:
        ranges = toc.get("top_level_ranges") or []
    return ranges if isinstance(ranges, list) else []


def _dedupe_same_start(
    entries: list[tuple[str, int, int]],
) -> list[tuple[str, int, int]]:
    """Same start_pdf_page → keep last title (usually the more specific nested one)."""
    by_start: dict[int, tuple[str, int, int]] = {}
    order: list[int] = []
    for title, start, end in entries:
        if start not in by_start:
            order.append(start)
        by_start[start] = (title, start, end)
    return [by_start[s] for s in sorted(order)]


def slices_from_toc(
    page_corpus: dict[str, Any],
    toc: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    """Build slices from TOC (or mechanical). Returns (slices, split_count)."""
    total = page_corpus["total_pdf_pages"]
    ranges = _toc_range_list(toc)
    slices: list[dict[str, Any]] = []

    if toc.get("toc_found") and ranges:
        cleaned: list[tuple[str, int, int]] = []
        for i, r in enumerate(ranges):
            if not isinstance(r, dict):
                continue
            title = (r.get("title") or f"section_{i}").strip()
            start = r.get("start_pdf_page")
            end = r.get("end_pdf_page")
            if not isinstance(start, int) or start < 1:
                continue
            start = min(start, total)
            if not isinstance(end, int) or end < start:
                end = -1
            cleaned.append((title, start, end if isinstance(end, int) else -1))

        cleaned = _dedupe_same_start(cleaned)

        for i, (title, start, end) in enumerate(cleaned):
            if end < 0:
                if i + 1 < len(cleaned):
                    end = max(start, cleaned[i + 1][1] - 1)
                else:
                    end = total
            end = min(max(end, start), total)
            cleaned[i] = (title, start, end)

        if cleaned and cleaned[0][1] > 1:
            sl = slice_from_pages(page_corpus, 1, cleaned[0][1] - 1)
            slices.append(
                _slice_row(
                    slice_id="front_matter",
                    title="front_matter",
                    source="front_matter",
                    sl=sl,
                )
            )

        for i, (title, start, end) in enumerate(cleaned):
            sl = slice_from_pages(page_corpus, start, end)
            slices.append(
                _slice_row(
                    slice_id=f"s{i + 1:02d}",
                    title=title,
                    source="toc",
                    sl=sl,
                )
            )

    if not slices:
        slices = mechanical_slices(page_corpus)
    return enforce_slice_max(page_corpus, slices)


def write_corpus_artifacts(
    doc_dir: Path, page_corpus: dict[str, Any], slices: list[dict]
) -> None:
    doc_dir.mkdir(parents=True, exist_ok=True)
    index = {k: v for k, v in page_corpus.items() if k != "corpus"}
    (doc_dir / "00_page_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (doc_dir / "00_corpus.txt").write_text(page_corpus["corpus"], encoding="utf-8")
    slice_dir = doc_dir / "01_slices"
    slice_dir.mkdir(exist_ok=True)
    meta = []
    for s in slices:
        (slice_dir / f"{s['slice_id']}.txt").write_text(s["text"], encoding="utf-8")
        meta.append({k: v for k, v in s.items() if k != "text"})
    (doc_dir / "01_inventory.json").write_text(
        json.dumps({"slices": meta, "slice_count": len(meta)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
