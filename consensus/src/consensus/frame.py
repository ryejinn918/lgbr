"""Multi-document consensus frame from report compress views."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from consensus.llm import DEFAULT_MODEL, chat, log


def build_consensus(
    compress_cards: list[dict[str, Any]],
    *,
    question: str,
    out_dir: Path,
    model: str = DEFAULT_MODEL,
) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    joined = "\n\n========\n\n".join(
        f"### COMPRESS: {c['slug']} | {Path(c.get('source_pdf') or '').name}\n"
        f"{c['compress']}"
        for c in compress_cards
    )
    log(f"consensus: reports={len(compress_cards)} chars={len(joined):,}")

    prompt = f"""Below are compress views from several broker reports.
Do the hard part: lock a **consensus frame** that can hold the whole bundle.

Question: {question}

In scope / out of scope:
- In scope: roof + major pillars where views converge. Fine numbers need not be filled yet.
- Out of scope: per-report summary dump, thin exec bullet lists, forcing an industry template.

Rules:
- One roof + 2–4 major pillars (faces of the same roof)
- Each pillar = one desk-owned axis: a single mechanism or value-chain segment,
  dense and precise — like one team part would cover it
- Do NOT merge unrelated fields into one pillar (keep them as separate pillars
  or move the weaker angle to Outside-the-frame)
- Each pillar: why it belongs + which body details are slots to fill later
- State overlap (consensus) vs one-sided angles
- Leave slots so the frame can grow with detail later
- Do not invent facts absent from the compress views
- Cite slug as provenance

Compress views:
{joined}

Output (English headers; Korean body OK for Korean sources):
# Consensus frame

## Roof
...

## Why this frame holds the bundle
...

## Major pillars
### 1. ...
- Role of this pillar:
- Consensus (which compress views support it):
- Slots to fill later:
### 2. ...
### 3. ...

## Outside-the-frame angles (side / weak)
...

## Body re-open priority (keywords)
1. ...
"""
    content, _ = chat(
        [
            {
                "role": "system",
                "content": (
                    "Lock a consensus FRAME from compressed multi-report views. "
                    "Structure over detail. No invented facts. "
                    "Keep each major pillar a single coherent axis — never mash "
                    "unrelated domains into one pillar. "
                    "English section headers; Korean body when sources are Korean."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        model=model,
        temperature=0.2,
        label="consensus",
        out_dir=out_dir,
    )
    if "Body re-open priority" not in content or "Major pillars" not in content:
        (out_dir / "04_consensus_frame.partial.md").write_text(content, encoding="utf-8")
        raise RuntimeError("consensus incomplete; saved partial")
    (out_dir / "04_consensus_frame.md").write_text(content, encoding="utf-8")
    log("consensus DONE")
    return content
