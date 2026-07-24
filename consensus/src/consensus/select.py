"""Select reports for consensus: AI uses LLM pack from audit cards; others QP."""

from __future__ import annotations

import json
from typing import Any

from consensus import runs_store
from consensus.llm import DEFAULT_MODEL, chat, log, parse_json

CORE_MAX = 10
AI_POOL_THEMES = ("ai", "datacenter")

ROLE_CORE = "selected"
ROLE_BIBLIO = "fill_extra"

SELECT_SYSTEM = """You build a research pack for an AI + AIDC industry consensus note.

You receive audit cards (title, topic, framework_summary, rationale) for quality-passed
sell-side notes. Choose which reports belong in the pack.

Goals:
- Cover diverse analytical axes across the pack (power/site, networking, inference infra,
  demand structure, etc.) so the consensus can have several major pillars.
- Prefer scarce, structural, mechanism-dense industry analyses over thin macro, asset
  allocation, or notes where AI is only seasoning.
- Do NOT name specific broker products or famous report brands in your reasoning.

Pillar discipline (critical):
- Diversity means multiple separate pillars later — NOT mixing unrelated fields into one axis.
- Each future pillar should feel like one desk/part could own it: one mechanism or one
  value-chain segment, precise and coherent.
- If two topics cannot sit in the same desk narrative, keep them as separate axes
  (or put the weaker one in bibliography / omit).

Limits:
- core: at most 10 report ids — these drive the consensus frame.
- bibliography: useful extras for detail-fill later (not in the frame). May be empty.
- Only use report_id values from the provided cards. No duplicates across core/bibliography.

Return JSON only:
{
  "core": [{"report_id": "...", "why": "..."}],
  "bibliography": [{"report_id": "...", "why": "..."}],
  "coverage_notes": "...",
  "pillar_sketch": ["axis 1...", "axis 2..."]
}
pillar_sketch: short list of non-overlapping axes the core pack can support.
"""


def _clip(s: Any, n: int) -> str:
    t = " ".join(str(s or "").split())
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


def build_audit_cards(pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for r in pool:
        qj = r.get("quality_json")
        if isinstance(qj, str):
            try:
                qj = json.loads(qj)
            except json.JSONDecodeError:
                qj = {}
        if not isinstance(qj, dict):
            qj = {}
        pub = r.get("published_at")
        cards.append(
            {
                "report_id": str(r["id"]),
                "title": str(r.get("title") or ""),
                "theme": str(r.get("theme") or ""),
                "page_count": r.get("page_count"),
                "published_at": pub.isoformat() if hasattr(pub, "isoformat") else str(pub or ""),
                "topic": _clip(qj.get("topic"), 200),
                "framework_summary": _clip(qj.get("framework_summary"), 500),
                "rationale": _clip(qj.get("rationale"), 400),
            }
        )
    return cards


def _pick_ids(
    items: Any,
    *,
    allowed: set[str],
    used: set[str],
    cap: int | None,
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        rid = str(it.get("report_id") or "").strip()
        if not rid or rid not in allowed or rid in used:
            continue
        why = _clip(it.get("why"), 300)
        out.append((rid, why))
        used.add(rid)
        if cap is not None and len(out) >= cap:
            break
    return out


def parse_pack_selection(
    raw: dict[str, Any],
    *,
    allowed_ids: set[str],
    core_max: int = CORE_MAX,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], dict[str, Any]]:
    """Return (core_pairs, biblio_pairs, meta) from model JSON."""
    used: set[str] = set()
    core = _pick_ids(raw.get("core"), allowed=allowed_ids, used=used, cap=core_max)
    biblio = _pick_ids(
        raw.get("bibliography"), allowed=allowed_ids, used=used, cap=None
    )
    sketch = raw.get("pillar_sketch")
    if not isinstance(sketch, list):
        sketch = []
    sketch_s = [_clip(x, 160) for x in sketch if str(x).strip()]
    meta = {
        "coverage_notes": _clip(raw.get("coverage_notes"), 1000),
        "pillar_sketch": sketch_s,
        "core_max": core_max,
    }
    return core, biblio, meta


def llm_select_ai_pack(
    cards: list[dict[str, Any]],
    *,
    model: str = DEFAULT_MODEL,
    core_max: int = CORE_MAX,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], dict[str, Any]]:
    if not cards:
        raise RuntimeError("no audit cards for AI pack selection")
    allowed = {c["report_id"] for c in cards}
    user = (
        f"Select a consensus pack. core_max={core_max}.\n\n"
        f"Cards JSON:\n{json.dumps(cards, ensure_ascii=False)}"
    )
    raw_text, _ = chat(
        [
            {"role": "system", "content": SELECT_SYSTEM},
            {"role": "user", "content": user},
        ],
        model=model,
        temperature=0.2,
        label="ai_pack_select",
    )
    parsed = parse_json(raw_text)
    core, biblio, meta = parse_pack_selection(
        parsed, allowed_ids=allowed, core_max=core_max
    )
    if not core:
        raise RuntimeError("AI pack selection returned empty core")
    log(f"ai_pack_select: core={len(core)} biblio={len(biblio)}")
    return core, biblio, meta


def _rows_by_id(pool: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(r["id"]): r for r in pool}


def select_for_theme(
    theme: str,
    *,
    model: str = DEFAULT_MODEL,
    core_max: int = CORE_MAX,
) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], str]], dict[str, Any]]:
    """Return (selected, excluded, criteria). selected has select_role set."""
    if theme == "ai":
        all_docs = runs_store.list_pool_reports(themes=AI_POOL_THEMES)
        qp = [r for r in all_docs if r.get("quality_pass") is True]
        non_qp = [
            (
                r,
                f"quality_pass={r.get('quality_pass')} scope={r.get('quality_scope')}",
            )
            for r in all_docs
            if r.get("quality_pass") is not True
        ]
        if not qp:
            raise RuntimeError("no quality_pass reports in AI pool")

        cards = build_audit_cards(qp)
        core_pairs, biblio_pairs, sel_meta = llm_select_ai_pack(
            cards, model=model, core_max=core_max
        )
        by_id = _rows_by_id(qp)
        selected: list[dict[str, Any]] = []
        for rid, why in core_pairs:
            row = dict(by_id[rid])
            row["select_role"] = ROLE_CORE
            row["select_why"] = why
            selected.append(row)
        for rid, why in biblio_pairs:
            row = dict(by_id[rid])
            row["select_role"] = ROLE_BIBLIO
            row["select_why"] = why
            selected.append(row)

        picked = {str(r["id"]) for r in selected}
        not_picked = [
            (r, "pack_omit") for r in qp if str(r["id"]) not in picked
        ]
        excluded = non_qp + not_picked
        criteria = {
            "quality_pass": True,
            "status": "downloaded",
            "theme": theme,
            "pool_themes": list(AI_POOL_THEMES),
            "select": "llm_audit_pack",
            "core_max": core_max,
            "core_count": len(core_pairs),
            "bibliography_count": len(biblio_pairs),
            "selected_count": len(selected),
            "excluded_count": len(excluded),
            "coverage_notes": sel_meta.get("coverage_notes"),
            "pillar_sketch": sel_meta.get("pillar_sketch"),
        }
        return selected, excluded, criteria

    all_docs = runs_store.list_theme_reports(theme)
    selected = [dict(r) for r in all_docs if r.get("quality_pass") is True]
    for r in selected:
        r["select_role"] = ROLE_CORE
    excluded = [
        (
            r,
            f"quality_pass={r.get('quality_pass')} scope={r.get('quality_scope')}",
        )
        for r in all_docs
        if r.get("quality_pass") is not True
    ]
    criteria = {
        "quality_pass": True,
        "status": "downloaded",
        "theme": theme,
        "selected_count": len(selected),
        "excluded_count": len(excluded),
    }
    return selected, excluded, criteria
