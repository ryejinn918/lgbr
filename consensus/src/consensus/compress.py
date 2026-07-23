"""Per-slice local compress → per-document report compress."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from consensus.corpus import sha256_text
from consensus.llm import DEFAULT_MODEL, chat, log


def _truncate(text: str, max_chars: int = 48_000) -> str:
    if len(text) <= max_chars:
        return text
    head = max_chars * 2 // 3
    tail = max_chars - head
    return text[:head] + "\n\n...[truncated]...\n\n" + text[-tail:]


def local_compress(
    slice_row: dict[str, Any],
    *,
    question: str,
    out_dir: Path,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    meta_in = {
        "slice_id": slice_row["slice_id"],
        "title": slice_row.get("title"),
        "page_start": slice_row["page_start"],
        "page_end": slice_row["page_end"],
        "char_start": slice_row["char_start"],
        "char_end": slice_row["char_end"],
        "char_len": slice_row["char_len"],
        "text_sha256": slice_row["text_sha256"],
    }
    prompt = f"""This is one slice of a broker research PDF.
Your job is NOT to discard content; turn it into a **mergeable card** for later aggregation.
Memo noise; do not delete sections here.

Question context: {question}

Slice meta (JSON):
{json.dumps(meta_in, ensure_ascii=False)}

Source text (may be Korean):
{_truncate(slice_row["text"])}

Markdown output (section headers in English; body may be Korean to match the source):
# slice {slice_row["slice_id"]}
## meta
- keep title / pages / char_len / text_sha256 as given
## claims and facts
- short, complete coverage of this slice
## numbers and dates
## proper nouns / keywords
- for later body re-open
## merge notes
- tables / repetition / promo — memo only, not deletion
"""
    content, usage = chat(
        [
            {
                "role": "system",
                "content": (
                    "Organize one report slice into a mergeable card. "
                    "Do not drop sections as noise. "
                    "Use English section headers; write body in Korean when the source is Korean."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        model=model,
        temperature=0.2,
        label=f"local_{slice_row['slice_id'][:24]}",
        out_dir=out_dir,
    )
    card = {
        **meta_in,
        "local_compress_md": content,
        "local_compress_sha256": sha256_text(content),
        "usage": usage,
    }
    (out_dir / f"02_local_{slice_row['slice_id']}.md").write_text(content, encoding="utf-8")
    return card


async def local_compress_all(
    slices: list[dict[str, Any]],
    *,
    question: str,
    out_dir: Path,
    model: str = DEFAULT_MODEL,
    concurrency: int = 4,
) -> list[dict[str, Any]]:
    sem = asyncio.Semaphore(concurrency)

    async def one(s: dict[str, Any]) -> dict[str, Any]:
        async with sem:
            return await asyncio.to_thread(
                local_compress, s, question=question, out_dir=out_dir, model=model
            )

    return list(await asyncio.gather(*[one(s) for s in slices]))


def report_compress(
    cards: list[dict[str, Any]],
    doc_meta: dict[str, Any],
    *,
    question: str,
    out_dir: Path,
    model: str = DEFAULT_MODEL,
) -> str:
    joined = "\n\n========\n\n".join(
        f"### CARD {c['slice_id']} | {c.get('title')} | "
        f"p{c['page_start']}-{c['page_end']} | chars={c['char_len']}\n"
        f"{c['local_compress_md']}"
        for c in cards
    )
    prompt = f"""Below are per-slice cards from one report.
Merge them **your way** into a single report-level compress view.
You decide what to keep central and what to de-emphasize.
Keep slice_id / page provenance next to key claims when possible.

Question: {question}
Document: {doc_meta.get("source_pdf")}
slug: {doc_meta.get("slug")}
corpus_char_len={doc_meta.get("corpus_char_len")} slices={len(cards)}

Cards:
{joined}

Output (English headers; Korean body OK for Korean sources):
# Report compress view
## One-line thesis
## Axes that split the world
## Must-keep numbers / claims (with slice_id)
## Angle unique to this report
## Candidates to re-open in the body (slice_id + keywords)
"""
    content, _ = chat(
        [
            {
                "role": "system",
                "content": (
                    "Merge slice cards into one report compress view. "
                    "Keep provenance. English headers; Korean body when source is Korean."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        model=model,
        temperature=0.2,
        label="report_compress",
        out_dir=out_dir,
    )
    (out_dir / "03_report_compress.md").write_text(content, encoding="utf-8")
    log(f"report_compress: wrote 03_report_compress.md ({len(content)} chars)")
    return content
