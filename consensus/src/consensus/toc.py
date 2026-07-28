"""Lite TOC probe from front pages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from consensus.corpus import front_pages_text
from consensus.llm import DEFAULT_MODEL, chat, log, parse_json

TOC_SYSTEM = """You inspect the opening pages of a Korean broker research PDF.
Find the summary table of contents if present, and recover EVERY TOC entry that has
an explicit destination page number — at any nesting depth (chapters, company
nameplates, numbered stock sections, etc.).

Omit nested lines that have NO page number (e.g. "1) …" under a chapter that only
lists subtitles without pages). Do not invent pages or sections.

Return exactly one JSON object (no markdown fences):
{
  "toc_found": true|false,
  "toc_pdf_pages": [1-based ints],
  "toc_ranges": [
    {
      "title": "verbatim TOC title",
      "start_pdf_page": 1,
      "end_pdf_page": 10,
      "level": 1
    }
  ]
}

Rules:
- Page numbers are 1-based physical PDF pages.
- If no real TOC, set toc_found=false and empty arrays.
- Include parent and child entries when both have page numbers (e.g. 기업분석 61,
  NAVER 62).
- end_pdf_page: prefer next listed start-1; last entry may use total_pdf_pages.
- level: 1 = top chapter, 2+ = nested (best effort; optional).
- Do not invent sections absent from the TOC.
- Keep JSON compact.
- Also accept legacy key top_level_ranges as an alias for toc_ranges if you emit it."""


def _extract_ranges(data: dict[str, Any]) -> list[dict[str, Any]]:
    ranges = data.get("toc_ranges")
    if not isinstance(ranges, list) or not ranges:
        ranges = data.get("top_level_ranges") or []
    if not isinstance(ranges, list):
        return []

    cleaned: list[dict[str, Any]] = []
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
        item: dict[str, Any] = {
            "title": title,
            "start_pdf_page": start,
            "end_pdf_page": end,
        }
        level = r.get("level")
        if isinstance(level, int) and level >= 1:
            item["level"] = level
        cleaned.append(item)
    return cleaned


async def probe_toc(
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
    raw, usage = await chat(
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
        data = {"toc_found": False, "toc_pdf_pages": [], "toc_ranges": []}

    if not isinstance(data, dict):
        data = {"toc_found": False, "toc_pdf_pages": [], "toc_ranges": []}

    found = bool(data.get("toc_found"))
    cleaned = _extract_ranges(data)

    if not found or not cleaned:
        result = {
            "toc_found": False,
            "toc_pdf_pages": [],
            "toc_ranges": [],
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
            "toc_ranges": cleaned,
            "top_level_ranges": cleaned,  # legacy mirror
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
