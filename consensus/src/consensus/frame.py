"""Multi-document consensus frame from report compress views."""

from __future__ import annotations

import json
from typing import Any
from pathlib import Path

from consensus.cite import HUMAN_CITE_RULE, human_doc_header
from consensus.llm import DEFAULT_MODEL, chat, log


async def build_consensus(
    compress_cards: list[dict[str, Any]],
    *,
    question: str,
    out_dir: Path,
    model: str = DEFAULT_MODEL,
    thesis: str | None = None,
    cut_logic: str | None = None,
    pillar_sketch: list[str] | None = None,
    external_evidence: str | None = None,
) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    joined = "\n\n========\n\n".join(
        f"### COMPRESS: {human_doc_header(provider=c.get('provider'), title=c.get('short_title') or c.get('title'), published_at=c.get('published_at'))}\n"
        f"{c['compress']}"
        for c in compress_cards
    )
    n_reports = len(compress_cards)
    providers = {
        str(c.get("provider") or "").strip()
        for c in compress_cards
        if str(c.get("provider") or "").strip()
    }
    n_providers = len(providers)
    log(
        f"consensus: reports={n_reports} providers={n_providers} "
        f"chars={len(joined):,}"
    )
    topics = [str(p).strip() for p in (pillar_sketch or []) if str(p).strip()]
    locked_block = ""
    if thesis or topics:
        locked_block = (
            "\nLocked cut (do not reinvent topics; Executive Summary and "
            "주제별 Deep Dive must follow this):\n"
            f"- thesis (핵심 긴장): {thesis or '—'}\n"
            f"- cut_logic: {cut_logic or '—'}\n"
            f"- topics (pillar_sketch): {json.dumps(topics, ensure_ascii=False)}\n"
        )

    prompt = f"""Below are compress views from several broker reports.
Lock a **consensus skeleton (골격)** that can hold the whole bundle.

Question: {question}
Pack facts (use these numbers; do not invent coverage %%):
- reports={n_reports}
- distinct_providers={n_providers}
{locked_block}
External evidence (FnGuide remains the primary view; use these only as corroboration, dissent, or supplement):
{external_evidence or '(none)'}

In scope / out of scope:
- In scope: Executive Summary + 2–4 topics (주제) where views converge.
  Fine numbers need not be filled yet — leave under 추후 보강.
- Out of scope: per-report summary dump, thin exec bullet lists,
  forcing a canned industry template.

Rules:
- Topics should be close to MECE: mutually distinct, jointly covering the tension.
  Do not pad topics that the compress views do not support.
- If locked topics (pillar_sketch) are provided, 주제별 Deep Dive MUST map to them
  (same cut; wording may be tightened, not replaced with a new taxonomy)
- Each topic = one desk-owned mechanism or value-chain segment
- Do NOT merge unrelated fields into one topic (keep separate, or move the weaker
  angle to 범위 밖 주제)
- Per topic: 선정 근거, agreement vs disagreement, and 추후 보강 slots
- Per topic, state the disagreement in one line (선정 근거 or 성장·저해).
  If houses agree, write "갈림 없음" once — do not only list agreements
- If a topic is effectively supported by a single house, say so in 선정 근거
  ("단일 출처") or shrink the weak angle into 범위 밖 주제
- Do not put items listed under 범위 밖 주제 back into that topic's
  현황/Evidence
- Do not invent facts absent from the compress views
- Do not treat external evidence as a replacement for FnGuide. Clearly separate the FnGuide view from external corroboration, dissent, and supplement.
- When external evidence disagrees with FnGuide, preserve the disagreement and explain the difference only when the supplied summaries support it.
- Keep number units and foreign-term spelling consistent within the document
- Do not write period-over-period change unless compress views explicitly compare
  periods; otherwise omit or put under 추후 보강 as defer
- {HUMAN_CITE_RULE}

Compress views:
{joined}

Output (section headers exactly as below; Korean body OK for Korean sources):
# 컨센서스 골격

## 분석 범위 및 커버리지
- 대상 리포트 수 / 증권사 수 (use pack facts above)
- 잠긴 주제가 묶음을 어떻게 커버하는지 (주제별 지지 감각; no invented %%)

## Executive Summary
...

## 주제별 Deep Dive
### 1. ...
- 주제 역할:
- 선정 근거:
- 현황 및 전망: (슬롯 — 비관~낙관 분포는 살붙임에서)
- 주요 플레이어: (슬롯, 국내 중심)
- 성장·저해 요인: (의견 갈림이 있으면 이유까지)
- 추후 보강:
### 2. ...
### 3. ...

## 범위 밖 주제
...

## 본문 재오픈 우선순위
1. ...
"""
    content, _ = await chat(
        [
            {
                "role": "system",
                "content": (
                    "Lock a consensus skeleton (골격) from compressed multi-report "
                    "views. Structure over detail. No invented facts. "
                    "Each Deep Dive topic must be a single coherent theme — never "
                    "mash unrelated domains into one topic. "
                    "Use the exact Korean/English section headers from the user "
                    "template. Korean body when sources are Korean. "
                    + HUMAN_CITE_RULE
                ),
            },
            {"role": "user", "content": prompt},
        ],
        model=model,
        temperature=0.2,
        label="consensus",
        out_dir=out_dir,
    )
    if "주제별 Deep Dive" not in content or "Executive Summary" not in content:
        (out_dir / "04_consensus_frame.partial.md").write_text(content, encoding="utf-8")
        raise RuntimeError("consensus incomplete; saved partial")
    (out_dir / "04_consensus_frame.md").write_text(content, encoding="utf-8")
    log("consensus DONE")
    return content
