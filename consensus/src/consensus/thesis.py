"""Cut sector axes (thesis) before report pack selection."""

from __future__ import annotations

import json
from typing import Any

from consensus import runs_store
from consensus.llm import DEFAULT_MODEL, chat, log, parse_json
from consensus.evidence_policy import is_evidence_eligible
from consensus.select import (
    THEME_LABEL_KO,
    THEME_SELECT_HINTS,
    build_audit_cards,
    pool_themes_for,
    _clip,
)

PILLAR_MIN = 2
PILLAR_MAX = 4


def thesis_system_prompt(theme: str) -> str:
    sector = THEME_LABEL_KO.get(theme, theme)
    hint = THEME_SELECT_HINTS.get(theme, "Prefer structural industry analyses.")
    return f"""You cut the analytical **topics (주제)** for a {sector} industry
consensus note.

You receive audit cards (topic, framework_summary, rationale) for quality-passed
sell-side notes. Do NOT choose which reports to keep. Only decide how the sector
is splitting right now.

Goal: one sharp industrial tension, then {PILLAR_MIN}–{PILLAR_MAX} non-overlapping
topics that follow from that cut — close to MECE, not a coverage catalog of every
theme in the pool. Do not pad topics the cards do not support. Do not force a
canned strategy matrix (e.g. BCG) onto the cut.

Sector cues ({sector}):
- {hint}

Write thesis, cut_logic, and pillar_sketch in Korean.

Rules:
- thesis: one sentence — what is diverging / binding capital or attention now.
- cut_logic: 2–4 short sentences — why these topics are separate (what you refuse
  to merge and why).
- pillar_sketch: {PILLAR_MIN}–{PILLAR_MAX} **주제** labels; each one desk-owned
  mechanism or value-chain segment. No report names, no broker names,
  no report_id/UUID. (JSON key stays pillar_sketch.)
- Do not invent facts absent from the cards; synthesize the cut from them.

Return JSON only:
{{
  "thesis": "...",
  "cut_logic": "...",
  "pillar_sketch": ["축 1...", "축 2..."]
}}
"""


def parse_thesis_cut(raw: dict[str, Any]) -> dict[str, Any]:
    thesis = _clip(raw.get("thesis"), 400)
    cut_logic = _clip(raw.get("cut_logic"), 1200)
    sketch = raw.get("pillar_sketch")
    if not isinstance(sketch, list):
        sketch = []
    pillars = [_clip(x, 160) for x in sketch if str(x).strip()]
    pillars = pillars[:PILLAR_MAX]
    if len(pillars) < PILLAR_MIN:
        raise RuntimeError(
            f"thesis cut needs {PILLAR_MIN}–{PILLAR_MAX} pillars, got {len(pillars)}"
        )
    if not thesis:
        raise RuntimeError("thesis cut missing thesis")
    return {
        "thesis": thesis,
        "cut_logic": cut_logic,
        "pillar_sketch": pillars,
    }


async def llm_cut_axes(
    cards: list[dict[str, Any]],
    *,
    theme: str,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    if not cards:
        raise RuntimeError("no audit cards for thesis cut")
    sector = THEME_LABEL_KO.get(theme, theme)
    llm_cards = [
        {
            "provider": c.get("provider"),
            "short_title": c.get("short_title"),
            "published_at": c.get("published_at"),
            "theme": c.get("theme"),
            "topic": c.get("topic"),
            "framework_summary": c.get("framework_summary"),
            "rationale": c.get("rationale"),
        }
        for c in cards
    ]
    user = (
        f"Cut axes for {sector}. Cards are evidence of what desks are writing — "
        f"not a checklist to cover.\n\n"
        f"Cards JSON:\n{json.dumps(llm_cards, ensure_ascii=False)}"
    )
    raw_text, _ = await chat(
        [
            {"role": "system", "content": thesis_system_prompt(theme)},
            {"role": "user", "content": user},
        ],
        model=model,
        temperature=0.3,
        label=f"{theme}_thesis_cut",
    )
    parsed = parse_json(raw_text)
    out = parse_thesis_cut(parsed)
    log(f"{theme}_thesis_cut: pillars={len(out['pillar_sketch'])}")
    return out


async def thesis_for_theme(
    theme: str,
    *,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Return criteria fragment with thesis / cut_logic / pillar_sketch."""
    if theme not in runs_store.THEMES:
        raise RuntimeError(f"invalid theme: {theme}")
    pool_themes = pool_themes_for(theme)
    all_docs = runs_store.list_pool_reports(themes=pool_themes)
    qp = [r for r in all_docs if is_evidence_eligible(r, theme=theme)]
    if not qp:
        raise RuntimeError(f"no eligible evidence reports in {theme} pool")
    cards = build_audit_cards(qp)
    cut = await llm_cut_axes(cards, theme=theme, model=model)
    return {
        "quality_pass": True,
        "theme": theme,
        "pool_themes": list(pool_themes),
        "thesis": cut["thesis"],
        "cut_logic": cut["cut_logic"],
        "pillar_sketch": cut["pillar_sketch"],
        "cut": "llm_thesis",
        "pool_qp_count": len(qp),
    }
