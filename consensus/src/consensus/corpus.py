"""PDF page corpus + TOC-based slicing."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pymupdf


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


def mechanical_slices(
    page_corpus: dict[str, Any],
    *,
    pages_per_slice: int = 4,
    max_chars: int = 24_000,
) -> list[dict[str, Any]]:
    """Page/char chunking when TOC is missing — keeps local_compress under truncate."""
    total = page_corpus["total_pdf_pages"]
    if total < 1:
        return []

    # Short docs: single whole slice is fine.
    full = slice_from_pages(page_corpus, 1, total)
    if total <= pages_per_slice and full["char_len"] <= max_chars:
        return [
            {
                "slice_id": "whole",
                "title": "whole_document",
                "source": "mechanical_short",
                **{k: full[k] for k in full if k != "text"},
                "text": full["text"],
            }
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
            {
                "slice_id": f"s{idx:02d}",
                "title": f"pages_{page}-{end}",
                "source": "mechanical",
                **{k: sl[k] for k in sl if k != "text"},
                "text": sl["text"],
            }
        )
        idx += 1
        page = end + 1
    return slices


def slices_from_toc(
    page_corpus: dict[str, Any],
    toc: dict[str, Any],
) -> list[dict[str, Any]]:
    total = page_corpus["total_pdf_pages"]
    ranges = toc.get("top_level_ranges") or []
    slices: list[dict[str, Any]] = []

    if toc.get("toc_found") and ranges:
        cleaned: list[tuple[str, int, int]] = []
        for i, r in enumerate(ranges):
            title = (r.get("title") or f"section_{i}").strip()
            start = r.get("start_pdf_page")
            end = r.get("end_pdf_page")
            if not isinstance(start, int) or start < 1:
                continue
            start = min(start, total)
            if not isinstance(end, int) or end < start:
                end = -1
            cleaned.append((title, start, end if isinstance(end, int) else -1))

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
                {
                    "slice_id": "front_matter",
                    "title": "front_matter",
                    "source": "front_matter",
                    **{k: sl[k] for k in sl if k != "text"},
                    "text": sl["text"],
                }
            )

        for i, (title, start, end) in enumerate(cleaned):
            sl = slice_from_pages(page_corpus, start, end)
            sid = f"s{i + 1:02d}"
            slices.append(
                {
                    "slice_id": sid,
                    "title": title,
                    "source": "toc",
                    **{k: sl[k] for k in sl if k != "text"},
                    "text": sl["text"],
                }
            )

    if not slices:
        slices = mechanical_slices(page_corpus)
    return slices


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
