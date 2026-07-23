"""Lite TOC probe from front pages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from consensus.corpus import front_pages_text
from consensus.llm import DEFAULT_MODEL, chat, log, parse_json

TOC_SYSTEM = """You inspect the opening pages of a Korean broker research PDF.
Find the summary table of contents if present, and recover only top-level sections
with destination page numbers. Ignore detailed nested subsection lists.

Return exactly one JSON object (no markdown fences):
{
  "toc_found": true|false,
  "toc_pdf_pages": [1-based ints],
  "top_level_ranges": [
    {
      "title": "verbatim TOC title",
      "start_pdf_page": 1,
      "end_pdf_page": 10
    }
  ]
}

Rules:
- Page numbers are 1-based physical PDF pages.
- If no real TOC, set toc_found=false and empty arrays.
- end_pdf_page: prefer next peer start-1; last entry may use total_pdf_pages.
- Do not invent sections absent from the TOC.
- Keep JSON compact."""


def probe_toc(
    page_corpus: dict[str, Any],
    *,
    window: int = 8,
    model: str = DEFAULT_MODEL,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    total = page_corpus["total_pdf_pages"]
    front = front_pages_text(page_corpus, window=window)
    prompt = (
        f"source_pdf={page_corpus.get('source_pdf')}\n"
        f"total_pdf_pages={total}\n"
        f"front_window_pages=1..{min(window, total)}\n\n"
        f"TEXT:\n{front}\n"
    )
    raw, usage = chat(
        [
            {"role": "system", "content": TOC_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        model=model,
        temperature=0.0,
        label="toc",
        out_dir=out_dir,
    )
    try:
        data = parse_json(raw)
    except Exception as exc:
        log(f"toc: parse failed ({exc}); fallback whole document")
        data = {"toc_found": False, "toc_pdf_pages": [], "top_level_ranges": []}

    if not isinstance(data, dict):
        data = {"toc_found": False, "toc_pdf_pages": [], "top_level_ranges": []}

    found = bool(data.get("toc_found"))
    ranges = data.get("top_level_ranges") or []
    if not isinstance(ranges, list):
        ranges = []

    cleaned = []
    for r in ranges:
        if not isinstance(r, dict):
            continue
        title = str(r.get("title") or "").strip()
        start = r.get("start_pdf_page")
        end = r.get("end_pdf_page")
        if not title or not isinstance(start, int):
            continue
        if not isinstance(end, int):
            end = None
        cleaned.append(
            {"title": title, "start_pdf_page": start, "end_pdf_page": end}
        )

    if not found or not cleaned:
        result = {
            "toc_found": False,
            "toc_pdf_pages": [],
            "top_level_ranges": [],
            "fallback": "whole_document",
            "total_pdf_pages": total,
            "raw": raw,
            "usage": usage,
        }
    else:
        result = {
            "toc_found": True,
            "toc_pdf_pages": data.get("toc_pdf_pages") or [],
            "top_level_ranges": cleaned,
            "fallback": None,
            "total_pdf_pages": total,
            "raw": raw,
            "usage": usage,
        }

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "00_toc.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return result
