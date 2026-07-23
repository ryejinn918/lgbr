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
    prompt = f"""이 슬라이스는 증권 리포트의 한 구간이다.
너의 일은 내용을 폐기하는 것이 아니라, 나중에 여러 슬라이스를 합칠 수 있게 **정리 카드**로 만드는 것이다.
노이즈는 메모만 하고, 여기서 구간을 삭제하지 마라.

질문 맥락: {question}

슬라이스 메타(JSON):
{json.dumps(meta_in, ensure_ascii=False)}

원문:
{_truncate(slice_row["text"])}

마크다운 출력:
# slice {slice_row["slice_id"]}
## meta
- title / pages / char_len / text_sha256 을 그대로
## 이 구간의 논지·사실 (빠짐없이 짧게 정리)
## 숫자·시점
## 고유명사·키워드 (나중에 본문 재오픈용)
## 합칠 때 참고 (표/반복/광고성 등 — 삭제가 아니라 메모)
"""
    content, usage = chat(
        [
            {
                "role": "system",
                "content": (
                    "Organize one report slice into a mergeable card. "
                    "Do not drop sections because you think they are noise. Korean."
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
    concurrency: int = 3,
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
    prompt = f"""아래는 한 리포트를 슬라이스별로 정리한 카드들이다.
너는 이 카드들을 **네 방식으로 합쳐** 리포트 단위 압축 뷰를 만들어라.
카드를 버릴지 말지, 무엇을 중심에 둘지는 네가 판단한다.
다만 합친 결과에서 각 핵심 주장 옆에 가능하면 slice_id / page 출처를 남겨라.

질문: {question}
문서: {doc_meta.get("source_pdf")}
slug: {doc_meta.get("slug")}
corpus_char_len={doc_meta.get("corpus_char_len")} slices={len(cards)}

카드들:
{joined}

출력:
# 리포트 압축 뷰
## 이 리포트의 관점(한 줄)
## 세상을 가르는 축
## 꼭 남는 숫자/주장 (출처 slice_id)
## 이 리포트만의 각도
## 본문을 더 열어야 할 후보 (slice_id + 키워드)
"""
    content, _ = chat(
        [
            {
                "role": "system",
                "content": (
                    "Merge slice cards into one report compress view in your own way. "
                    "Keep provenance. Korean."
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
