"""Select reports for consensus: LLM pack from quality-pass audit cards (all themes)."""

from __future__ import annotations

import json
from typing import Any

from consensus import runs_store
from consensus.llm import DEFAULT_MODEL, chat, log, parse_json
from consensus.runs_store import PERIOD_MONTHS_DEFAULT

CORE_MAX = 10
AI_POOL_THEMES = ("ai", "datacenter")

ROLE_CORE = "selected"
ROLE_BIBLIO = "fill_extra"

THEME_LABEL_KO = {
    "datacenter": "데이터센터",
    "ai": "AI·AIDC",
    "physical_ai": "피지컬 AI",
}

# Extra sector cues for the pack LLM (English; output fields stay Korean).
THEME_SELECT_HINTS = {
    "ai": (
        "Axes often include power/site, networking, inference infra, demand structure. "
        "Prefer scarce, structural, mechanism-dense industry analyses over thin macro, "
        "asset allocation, or notes where AI is only seasoning."
    ),
    "datacenter": (
        "Axes often include power/site/cooling, capacity and demand, operators vs "
        "equipment/value-chain. Prefer mechanism-dense industry notes over thin "
        "macro or one-name equity briefs."
    ),
    "physical_ai": (
        "Axes often include robotics, factory automation, sensors/actuators, and "
        "deployment constraints. Prefer structural industry analyses over thin "
        "thematic or equity-only notes."
    ),
}


def pool_themes_for(theme: str) -> tuple[str, ...]:
    if theme == "ai":
        return AI_POOL_THEMES
    return (theme,)


def select_system_prompt(theme: str) -> str:
    sector = THEME_LABEL_KO.get(theme, theme)
    hint = THEME_SELECT_HINTS.get(theme, "Prefer structural industry analyses.")
    return f"""You build a research pack for a {sector} industry consensus note.

You receive audit cards (title, topic, framework_summary, rationale) for quality-passed
sell-side notes. Choose which reports belong in the pack.

Language (mandatory):
- Write coverage_notes, pillar_sketch, and every why field in Korean.

Sector focus ({sector}):
- {hint}

Goals:
- Cover diverse analytical axes across the pack so the consensus can have several
  major pillars.
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
- Do NOT list every omitted report_id. No omitted[] array.
- Even if the pool is small, still assign why for every chosen report; put weaker
  duplicates in bibliography or omit with a typed reason in coverage_notes.

coverage_notes (Korean, short paragraphs):
1) What the pack covers (axes / balance).
2) Omit summary: main types of quality-passed notes left out and why
   (e.g. thin macro, duplicate axis, off-theme). Types and representative reasons only —
   never enumerate all omitted titles.

Return JSON only:
{{
  "core": [{{"report_id": "...", "why": "..."}}],
  "bibliography": [{{"report_id": "...", "why": "..."}}],
  "coverage_notes": "...",
  "pillar_sketch": ["축 1...", "축 2..."]
}}
pillar_sketch: short Korean list of non-overlapping axes the core pack can support.
"""


# Backward-compatible name used in tests / imports.
SELECT_SYSTEM = select_system_prompt("ai")


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


def llm_select_pack(
    cards: list[dict[str, Any]],
    *,
    theme: str,
    model: str = DEFAULT_MODEL,
    core_max: int = CORE_MAX,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], dict[str, Any]]:
    if not cards:
        raise RuntimeError("no audit cards for pack selection")
    allowed = {c["report_id"] for c in cards}
    sector = THEME_LABEL_KO.get(theme, theme)
    user = (
        f"Select a consensus pack for {sector}. core_max={core_max}.\n\n"
        f"Cards JSON:\n{json.dumps(cards, ensure_ascii=False)}"
    )
    raw_text, _ = chat(
        [
            {"role": "system", "content": select_system_prompt(theme)},
            {"role": "user", "content": user},
        ],
        model=model,
        temperature=0.2,
        label=f"{theme}_pack_select",
    )
    parsed = parse_json(raw_text)
    core, biblio, meta = parse_pack_selection(
        parsed, allowed_ids=allowed, core_max=core_max
    )
    if not core:
        raise RuntimeError(f"{theme} pack selection returned empty core")
    log(f"{theme}_pack_select: core={len(core)} biblio={len(biblio)}")
    return core, biblio, meta


# Alias kept for older call sites / notebooks.
llm_select_ai_pack = llm_select_pack


def _rows_by_id(pool: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(r["id"]): r for r in pool}


def select_for_theme(
    theme: str,
    *,
    model: str = DEFAULT_MODEL,
    core_max: int = CORE_MAX,
) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], str]], dict[str, Any]]:
    """Return (selected, excluded, criteria). selected has select_role + select_why."""
    if theme not in runs_store.THEMES:
        raise RuntimeError(f"invalid theme: {theme}")

    pool_themes = pool_themes_for(theme)
    all_docs = runs_store.list_pool_reports(themes=pool_themes)
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
        raise RuntimeError(f"no quality_pass reports in {theme} pool")

    cards = build_audit_cards(qp)
    core_pairs, biblio_pairs, sel_meta = llm_select_pack(
        cards, theme=theme, model=model, core_max=core_max
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
    not_picked = [(r, "pack_omit") for r in qp if str(r["id"]) not in picked]
    excluded = non_qp + not_picked
    criteria = {
        "quality_pass": True,
        "status": "downloaded",
        "theme": theme,
        "pool_themes": list(pool_themes),
        "period_months": PERIOD_MONTHS_DEFAULT,
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
