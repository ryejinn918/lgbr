"""Select reports for consensus: LLM pack from quality-pass audit cards (all themes)."""

from __future__ import annotations

import json
from typing import Any

from consensus import runs_store
from consensus.cite import (
    format_published_at,
    resolve_short_title,
    short_provider,
)
from consensus.llm import DEFAULT_MODEL, chat, log, parse_json
from consensus.runs_store import PERIOD_MONTHS_DEFAULT

CORE_MAX = 10
AI_POOL_THEMES = ("ai",)
COVERAGE_NOTES_MAX = 2500

ROLE_CORE = "selected"
ROLE_BIBLIO = "fill_extra"

THEME_LABEL_KO = {
    "ai": "AI",
    "datacenter": "데이터센터",
    "macroeconomy": "거시경제",
    "physical_ai": "피지컬 AI",
    "appliance": "가전",
    "display": "디스플레이",
    "automotive": "자동차",
    "petrochemical": "석유화학",
}

# Extra sector cues for the pack LLM (English; output fields stay Korean).
THEME_SELECT_HINTS = {
    "ai": (
        "Axes often include models/LLM, AI semiconductors, inference software, "
        "and AI demand structure. Prefer mechanism-dense industry analyses; "
        "exclude pure data-center/power/cooling notes (those belong to datacenter) "
        "and thin macro/asset-allocation pieces."
    ),
    "datacenter": (
        "Axes often include AIDC power/site/cooling, networking, colo capacity, "
        "and infra bottlenecks. Prefer scarce structural industry analyses over "
        "thin equity-only or generic AI hype notes."
    ),
    "macroeconomy": (
        "Axes often include growth/inflation, rates/FX, credit cycles, and "
        "cross-asset implications. Prefer structural macro / asset-allocation "
        "frameworks. Exclude AI-industry or AIDC notes where macro is only backdrop; "
        "exclude single-sector or single-name notes."
    ),
    "physical_ai": (
        "Axes often include robotics, factory automation, sensors/actuators, and "
        "deployment constraints. Prefer structural industry analyses over thin "
        "thematic or equity-only notes."
    ),
    "appliance": (
        "Axes often include demand cycles, channel/mix, component cost, and "
        "regional competition. Prefer structural industry analyses over thin "
        "single-name or promo-driven notes."
    ),
    "display": (
        "Axes often include panel supply/demand, technology migration (OLED/LCD), "
        "equipment/materials, and end-market mix. Prefer mechanism-dense industry "
        "notes over thin equity-only briefs."
    ),
    "automotive": (
        "Axes often include EV/ICE mix, parts/value-chain, demand and policy, and "
        "OEM vs supplier dynamics. Prefer structural industry analyses over thin "
        "thematic or single-name notes."
    ),
    "petrochemical": (
        "Axes often include feedstock spreads, capacity cycles, downstream demand, "
        "and China/global supply. Prefer mechanism-dense industry notes over thin "
        "macro or equity-only briefs."
    ),
}


def pool_themes_for(theme: str) -> tuple[str, ...]:
    """Pool membership themes for a consensus tab (ai is ai-only)."""
    if theme == "ai":
        return AI_POOL_THEMES
    return (theme,)


def select_system_prompt(theme: str) -> str:
    sector = THEME_LABEL_KO.get(theme, theme)
    hint = THEME_SELECT_HINTS.get(theme, "Prefer structural industry analyses.")
    return f"""You place quality-passed sell-side notes into a **fixed topic pack**
for a {sector} industry consensus note.

Topics are already decided (thesis + pillar_sketch as topic labels).
Do NOT reinvent or rename topics. Your job is placement: which reports fill
which topic holes.

Language (mandatory):
- Write coverage_notes and every why field in Korean.
- Never use report_id, full title, UUID, or hex in prose. report_id belongs
  only in core[].report_id and bibliography[].report_id.

why (per report; UI already shows title/provider — do not name or cite the report):
- 1–2 Korean sentences: which locked **주제(topic)** it serves (or why 보조문헌)
  and what contribution it adds. No report names, no [provider] tags.

coverage_notes (pack summary — naming other reports is OK):
- Allowed name fields: provider, short_title, published_at.
- Prefer the broker as the sentence subject when natural; put the source tag
  in square brackets (use () only for ordinary parentheticals).
- Always lead with provider inside []. If unambiguous, [provider] alone
  e.g. [IBK]. Otherwise [provider, short_title]
  e.g. [IBK, 자동차/2차전지 Monthly].
- If still ambiguous (same series), add published_at:
  [provider, short_title, published_at].
- Do not cite short_title alone.

Sector focus ({sector}):
- {hint}

Placement goals:
- For each locked topic, pick **주요문헌(core) 1–2 reports** that densest cover it;
  put reinforcing notes in bibliography as **보조문헌**.
- A topic covered uniquely/densely by a single report may still be 주요문헌
  (emerging trend / scarce mechanism) — do not require two hubs.
- Do not force a hub onto every topic if the pool is thin.
- why must say which locked topic the report serves (or why 보조문헌).
- Do NOT invent new topic names.

Limits:
- core (주요문헌): at most 10 report ids — these drive the consensus skeleton.
- bibliography (보조문헌): useful extras for detail-fill later. May be empty.
- Only use report_id values from the provided cards. No duplicates across core/bibliography.
- Do NOT list every omitted report_id. No omitted[] array.
- Do NOT return pillar_sketch (topics are locked upstream).

coverage_notes (Korean, short paragraphs — readability first):
1) Opening: restate the locked thesis in one sentence (no broker/report names).
2) How 주요문헌 vs 보조문헌 covers the locked topics (counts / balance) —
   no stacked titles.
3) Omit summary vs the locked tension (duplicate series, off-theme, single-name,
   thin macro). Types and reasons only.
4) Optional last line: compact [provider, short_title] tags for representatives.

Return JSON only:
{{
  "core": [{{"report_id": "...", "why": "..."}}],
  "bibliography": [{{"report_id": "...", "why": "..."}}],
  "coverage_notes": "..."
}}
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
        title = str(r.get("title") or "")
        cards.append(
            {
                "report_id": str(r["id"]),
                "provider": short_provider(str(r.get("provider") or "")),
                "short_title": resolve_short_title(title, quality_json=qj),
                "title": title,
                "theme": str(r.get("theme") or ""),
                "page_count": r.get("page_count"),
                "published_at": format_published_at(r.get("published_at")),
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
    locked_pillars: list[str] | None = None,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], dict[str, Any]]:
    """Return (core_pairs, biblio_pairs, meta) from model JSON."""
    used: set[str] = set()
    core = _pick_ids(raw.get("core"), allowed=allowed_ids, used=used, cap=core_max)
    biblio = _pick_ids(
        raw.get("bibliography"), allowed=allowed_ids, used=used, cap=None
    )
    pillars = [p for p in (locked_pillars or []) if str(p).strip()]
    meta = {
        "coverage_notes": _clip(raw.get("coverage_notes"), COVERAGE_NOTES_MAX),
        "pillar_sketch": pillars,
        "core_max": core_max,
    }
    return core, biblio, meta


async def llm_select_pack(
    cards: list[dict[str, Any]],
    *,
    theme: str,
    thesis: str,
    cut_logic: str,
    pillar_sketch: list[str],
    model: str = DEFAULT_MODEL,
    core_max: int = CORE_MAX,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], dict[str, Any]]:
    if not cards:
        raise RuntimeError("no audit cards for pack selection")
    pillars = [str(p).strip() for p in pillar_sketch if str(p).strip()]
    if len(pillars) < 2:
        raise RuntimeError("select requires locked pillar_sketch (2+)")
    if not str(thesis or "").strip():
        raise RuntimeError("select requires locked thesis")
    allowed = {c["report_id"] for c in cards}
    sector = THEME_LABEL_KO.get(theme, theme)
    llm_cards = [
        {
            "provider": c.get("provider"),
            "short_title": c.get("short_title"),
            "published_at": c.get("published_at"),
            "title": c.get("title"),
            "theme": c.get("theme"),
            "page_count": c.get("page_count"),
            "topic": c.get("topic"),
            "framework_summary": c.get("framework_summary"),
            "rationale": c.get("rationale"),
            "report_id": c.get("report_id"),
        }
        for c in cards
    ]
    locked = {
        "thesis": thesis,
        "cut_logic": cut_logic,
        "pillar_sketch": pillars,
    }
    user = (
        f"Place reports into the locked pack for {sector}. core_max={core_max}.\n"
        "Topics (pillar_sketch) are fixed — do not rename them.\n"
        "Per topic: 1–2 주요문헌 (core), rest 보조문헌 (bibliography) when useful.\n"
        "In coverage_notes, name other reports with provider-first square "
        "brackets: `[provider]` if unambiguous, else `[provider, short_title]` or "
        "`[provider, short_title, published_at]`. "
        "In why: topic contribution only — do not name or cite the report.\n\n"
        f"Locked axes JSON:\n{json.dumps(locked, ensure_ascii=False)}\n\n"
        f"Cards JSON:\n{json.dumps(llm_cards, ensure_ascii=False)}"
    )
    raw_text, _ = await chat(
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
        parsed,
        allowed_ids=allowed,
        core_max=core_max,
        locked_pillars=pillars,
    )
    if not core:
        raise RuntimeError(f"{theme} pack selection returned empty core")
    log(f"{theme}_pack_select: core={len(core)} biblio={len(biblio)}")
    return core, biblio, meta


# Alias kept for older call sites / notebooks.
llm_select_ai_pack = llm_select_pack


def _rows_by_id(pool: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(r["id"]): r for r in pool}


async def select_for_theme(
    theme: str,
    *,
    thesis: str,
    cut_logic: str,
    pillar_sketch: list[str],
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
    core_pairs, biblio_pairs, sel_meta = await llm_select_pack(
        cards,
        theme=theme,
        thesis=thesis,
        cut_logic=cut_logic,
        pillar_sketch=pillar_sketch,
        model=model,
        core_max=core_max,
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
        "thesis": str(thesis or "").strip(),
        "cut_logic": str(cut_logic or "").strip(),
        "pillar_sketch": sel_meta.get("pillar_sketch") or list(pillar_sketch),
    }
    return selected, excluded, criteria
