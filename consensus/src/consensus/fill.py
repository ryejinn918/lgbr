"""Fill locked consensus frame by reopening report slices (slice-addressed)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from consensus.cite import HUMAN_CITE_RULE, human_doc_header
from consensus.llm import DEFAULT_MODEL, chat, log, parse_json

SLICE_CHAR_CAP = 12_000

# New LG-facing label + legacy English (older frames / filled drafts).
_SLOT_LABEL = r"(?:추후 보강|Slots to fill later)"
_SLOT_BLOCK_RE = re.compile(
    rf"(?m)^([ \t]*[-*][ \t]+)?\*\*{_SLOT_LABEL}\*\*[^\n]*\n"
    r"(?:[ \t]*[-*][ \t]+[^\n]*\n|[ \t]+\S[^\n]*\n)*"
)
# Also match unbolded "추후 보강:" lines from the new frame template.
_SLOT_LINE_RE = re.compile(
    rf"(?ims)^[ \t]*[-*]?[ \t]*\*\*{_SLOT_LABEL}\*\*[^\n]*\n(.*?)(?=\n### |\n## |\Z)"
    rf"|^[ \t]*[-*]?[ \t]*{_SLOT_LABEL}\s*:[^\n]*\n(.*?)(?=\n### |\n## |\Z)"
)
_STILL_EMPTY_SPLIT_RE = re.compile(
    r"(?m)^(## (?:미충족 보강|Still-empty slots)\b.*)$"
)


def extract_target_slots(frame: str) -> list[str]:
    """Collect bullet items under per-topic 추후 보강 (or legacy Slots)."""
    slots: list[str] = []
    for m in _SLOT_LINE_RE.finditer(frame or ""):
        block = m.group(1) if m.group(1) is not None else m.group(2)
        if not block:
            continue
        for line in block.splitlines():
            s = line.strip()
            if s.startswith(("-", "*")):
                item = s.lstrip("-*").strip()
                if item:
                    slots.append(item)
    return slots


def strip_slot_sections(frame: str) -> str:
    """Remove per-topic 추후 보강 / legacy Slots blocks from a frame draft."""
    if not frame:
        return frame
    out = _SLOT_BLOCK_RE.sub("", frame)
    # Unbolded "추후 보강:" blocks (new frame template).
    out = re.sub(
        r"(?ims)^[ \t]*[-*]?[ \t]*추후 보강\s*:[^\n]*\n"
        r"(?:[ \t]*[-*][ \t]+[^\n]*\n|[ \t]+\S[^\n]*\n)*",
        "",
        out,
    )
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip() + "\n"


def strip_pillar_slots_from_filled(content: str) -> tuple[str, bool]:
    """Strip illegal per-topic 추후 보강 blocks from filled output.

    Keeps a top-level ``## 미충족 보강`` / ``## Still-empty slots`` section.
    Returns (cleaned, did_strip).
    """
    if not content:
        return content, False
    parts = _STILL_EMPTY_SPLIT_RE.split(content, maxsplit=1)
    head = parts[0]
    tail = "".join(parts[1:]) if len(parts) > 1 else ""
    cleaned_head, n = _SLOT_BLOCK_RE.subn("", head)
    cleaned_head2, n2 = re.subn(
        r"(?ims)^[ \t]*[-*]?[ \t]*추후 보강\s*:[^\n]*\n"
        r"(?:[ \t]*[-*][ \t]+[^\n]*\n|[ \t]+\S[^\n]*\n)*",
        "",
        cleaned_head,
    )
    if n == 0 and n2 == 0:
        return content, False
    cleaned_head2 = re.sub(r"\n{3,}", "\n\n", cleaned_head2)
    return (cleaned_head2.rstrip() + "\n\n" + tail.lstrip()).rstrip() + "\n", True


def open_slice_body(text: str, *, cap: int = SLICE_CHAR_CAP) -> str:
    """Return slice text for fill; head-truncate if over cap."""
    text = text or ""
    if len(text) <= cap:
        return text
    return text[:cap] + f"\n\n...[truncated at {cap} chars; slice longer]...\n"


def _slice_inventory(doc_dir: Path) -> list[str]:
    inv = doc_dir / "01_inventory.json"
    if inv.is_file():
        try:
            data = json.loads(inv.read_text(encoding="utf-8"))
            ids = [
                str(s.get("slice_id"))
                for s in (data.get("slices") or [])
                if s.get("slice_id")
            ]
            if ids:
                return ids
        except (json.JSONDecodeError, OSError):
            pass
    return sorted(p.stem for p in (doc_dir / "01_slices").glob("*.txt"))


def _extract_reopen_section(compress_md: str) -> str:
    """Pull the re-open candidates section from a report compress view."""
    text = compress_md or ""
    patterns = (
        r"(?im)^##\s*.*(?:re-?open|본문을 더 열|Candidates to re-open).*$",
        r"(?im)^##\s*.*후보.*$",
    )
    for pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        start = m.start()
        nxt = re.search(r"(?m)^##\s+", text[m.end() :])
        end = m.end() + nxt.start() if nxt else len(text)
        section = text[start:end].strip()
        if len(section) > 40:
            return section[:4000]
    return text[-2000:] if text else "(no compress)"


def _build_reopen_index(
    compress_cards: list[dict[str, Any]],
    slug_to_dir: dict[str, Path],
) -> tuple[str, dict[str, list[str]]]:
    """Return prompt block + slug→valid slice_ids map."""
    slug_slices: dict[str, list[str]] = {}
    blocks: list[str] = []
    for card in compress_cards:
        slug = str(card.get("slug") or "")
        if not slug:
            continue
        doc_dir = slug_to_dir.get(slug) or Path(str(card.get("cache_dir") or ""))
        ids = _slice_inventory(doc_dir) if doc_dir and doc_dir.is_dir() else []
        slug_slices[slug] = ids
        reopen = _extract_reopen_section(str(card.get("compress") or ""))
        label = human_doc_header(
            provider=card.get("provider"),
            title=card.get("short_title") or card.get("title"),
            published_at=card.get("published_at"),
        )
        blocks.append(
            f"### INDEX slug={slug} | {label}\n"
            f"valid_slice_ids: {json.dumps(ids, ensure_ascii=False)}\n"
            f"{reopen}\n"
        )
    return "\n========\n".join(blocks), slug_slices


def _resolve_slug(slug: str, slug_to_dir: dict[str, Path]) -> tuple[str | None, Path | None]:
    if slug in slug_to_dir:
        return slug, slug_to_dir[slug]
    for k, d in slug_to_dir.items():
        if slug and (slug in k or k in slug):
            return k, d
    return None, None


def _coerce_slice_id(slice_id: str, valid: list[str]) -> str | None:
    if not valid:
        return None
    sid = (slice_id or "").strip()
    if sid in valid:
        return sid
    if sid == "whole" and "whole" not in valid:
        non_fm = [v for v in valid if v != "front_matter"]
        return non_fm[0] if non_fm else valid[0]
    if re.fullmatch(r"s\d+", sid):
        padded = f"s{int(sid[1:]):02d}"
        if padded in valid:
            return padded
    return valid[0]


async def fill_frame(
    frame: str,
    slug_to_dir: dict[str, Path],
    *,
    question: str,
    out_dir: Path,
    model: str = DEFAULT_MODEL,
    compress_cards: list[dict[str, Any]] | None = None,
    external_evidence: str | None = None,
) -> tuple[str, dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cards = compress_cards or []
    reopen_index, slug_slices = _build_reopen_index(cards, slug_to_dir)
    if not reopen_index:
        parts = []
        for slug, doc_dir in sorted(slug_to_dir.items()):
            ids = _slice_inventory(doc_dir)
            slug_slices[slug] = ids
            parts.append(
                f"### INDEX slug={slug}\n"
                f"valid_slice_ids: {json.dumps(ids, ensure_ascii=False)}\n"
            )
        reopen_index = "\n========\n".join(parts)

    (out_dir / "05_reopen_index.md").write_text(reopen_index, encoding="utf-8")

    target_slots = extract_target_slots(frame)
    structure_frame = strip_slot_sections(frame)
    slots_block = (
        "\n".join(f"- {s}" for s in target_slots)
        if target_slots
        else "- (no explicit slots; thicken pillars from OPEN bodies)"
    )
    (out_dir / "05_target_slots.md").write_text(slots_block + "\n", encoding="utf-8")

    plan_raw, _ = await chat(
        [
            {
                "role": "system",
                "content": (
                    "Output JSON only. Plan which report slices to open to fill "
                    "TARGET SLOTS. Use ONLY slugs and slice_ids from the reopen index. "
                    "Do not invent keywords or queries — address slices only."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question: {question}\\n\\n"
                    f"## Frame structure (titles to preserve)\n{structure_frame}\n\n"
                    f"## TARGET SLOTS to fill\n{slots_block}\n\n"
                    "Reopen index (compress candidates + valid slice_ids).\n"
                    "Rules:\n"
                    "- Pick slug + slice_id only (no queries).\n"
                    "- slice_id MUST be one of that slug's valid_slice_ids "
                    "(never invent whole/s05 if absent).\n"
                    "- Prefer slice_ids named in the reopen candidates for each slot.\n"
                    "- Cover TARGET SLOTS / body re-open priority; one open per slot "
                    "when possible.\n"
                    "JSON:\n"
                    '{"opens":[{"slug":"...","slice_id":"s01",'
                    '"slot":"pillar/slot","why":"..."}]}\n\n'
                    f"## Reopen index\n{reopen_index}"
                ),
            },
        ],
        model=model,
        temperature=0.15,
        label="fill_plan",
        out_dir=out_dir,
    )
    plan = parse_json(plan_raw)
    opens = plan.get("opens") or []
    log(f"fill: opens={len(opens)}")

    dossiers: list[dict[str, Any]] = []
    for i, op in enumerate(opens, 1):
        raw_slug = (op.get("slug") or "").strip()
        slug, doc_dir = _resolve_slug(raw_slug, slug_to_dir)
        if doc_dir is None or slug is None:
            log(f"  skip open {i}: unknown slug={op.get('slug')}")
            continue

        valid = slug_slices.get(slug) or _slice_inventory(doc_dir)
        coerced = _coerce_slice_id(str(op.get("slice_id") or ""), valid)
        if not coerced:
            log(f"  skip open {i}: no slices in {slug}")
            continue
        if coerced != (op.get("slice_id") or "").strip():
            log(
                f"  open {i}: slice coerce "
                f"{op.get('slice_id')!r} → {coerced!r} valid={valid}"
            )

        slice_path = doc_dir / "01_slices" / f"{coerced}.txt"
        if not slice_path.is_file():
            candidates = sorted((doc_dir / "01_slices").glob("*.txt"))
            if not candidates:
                log(f"  skip open {i}: missing file {slug}/{coerced}")
                continue
            slice_path = candidates[0]
            coerced = slice_path.stem
            log(f"  open {i}: slice file fallback → {coerced}")

        text = slice_path.read_text(encoding="utf-8")
        body = open_slice_body(text)
        log(f"  open [{i}] {slug}/{coerced} slice_chars={len(text)} used={len(body)}")
        dossiers.append(
            {
                "slug": slug,
                "slice_id": coerced,
                "slot": op.get("slot"),
                "why": op.get("why"),
                "body": body,
                "slice_chars": len(text),
            }
        )
        (out_dir / f"05_open_{i}.txt").write_text(body, encoding="utf-8")

    if not dossiers:
        raise RuntimeError("fill: no body opens succeeded")

    slug_label = {
        str(c.get("slug") or ""): human_doc_header(
            provider=c.get("provider"),
            title=c.get("short_title") or c.get("title"),
            published_at=c.get("published_at"),
        )
        for c in cards
        if c.get("slug")
    }
    dossier_txt = "\n\n========\n\n".join(
        f"### OPEN {slug_label.get(d['slug'], '보고서')} | "
        f"slot={d['slot']} | why={d['why']}\n"
        f"{d['body']}"
        for d in dossiers
    )

    evidence_notice = ""
    theme_hint = str(question or "").lower()

    if any(
        marker in theme_hint
        for marker in ("appliance", "display", "가전", "디스플레이")
    ):
        evidence_notice = (
            "자료 유의사항\n"
            "본 분석은 FnGuide 및 확보 가능한 보완 자료를 기준으로 작성되었습니다. "
            "산업 전체를 직접 다루는 보고서가 제한적이어서 "
            "기업·제품·기술 중심 자료를 보완적으로 활용했습니다.\n\n"
        )

    prompt = f"""Preserve the locked skeleton's Executive Summary and 주제 titles.
Thicken each 주제 using **only** sentences/numbers that actually appear in the
OPEN bodies below.
Never invent numbers, company facts, or prices missing from OPEN.
Absorb filled TARGET SLOTS into Evidence — do **not** copy "추후 보강"
(or legacy "Slots to fill later") under topics.
{HUMAN_CITE_RULE}
Use each OPEN header's human label in footnotes.
Keep number units and foreign-term spelling consistent.
Evidence: when natural, group bullets under 2–3 mechanism branches; if they do
not group cleanly, leave a flat list — do not invent a taxonomy.
Claim: if it follows one house, add only a short time-axis/condition phrase
that appears in OPEN (no new synthesis).
Players/macros that do not support the Claim: drop or one Watch line.
Outlook: only if OPEN supports it, note 비관~낙관 distribution with footnotes.
Players: domestic first; include global/unlisted only when OPEN names them.
Growth/headwinds: emphasize disagreements and why they diverge.

The output must be a **standalone, self-contained document**. Forbidden shorthand:
(unchanged), same as above, as in locked frame, 중략, 생략, and similar.

Question: {question}

## External evidence (FnGuide is primary; classify as corroboration, dissent, or supplement)
{external_evidence or '(none)'}

## Frame structure (titles to preserve; rewrite fully)
{structure_frame}

## TARGET SLOTS (fill from OPEN; omit from output if filled)
{slots_block}

## Opened slice bodies
{dossier_txt}

{evidence_notice}

Output (section headers exactly as below; Korean body OK for Korean sources):
# 살 붙인 논지

## Executive Summary
(full prose)

## 주제별 Deep Dive
### 1. (existing topic title)
- **주제 역할**
- **Claim**
- **Evidence (number / date; end each bullet with short footnote)**
- **현황 및 전망** (비관~낙관; OPEN에 있을 때만)
- **주요 플레이어**
- **성장·저해 요인**
- **Watch**
(dense; self-contained; NO 추후 보강 under topics)

## 미충족 보강 (다른 출처로 미룸)
- Only TARGET SLOTS not supported by OPEN bodies. One follow-up query each.

## 참고 보고서
...
"""

    content, _ = await chat(
        [
            {
                "role": "system",
                "content": (
                    "Enrich a locked consensus skeleton with opened report slice "
                    "bodies. Keep Executive Summary and 주제 titles. Grow density. "
                    "No invented facts. Prefer grouping Evidence into a few "
                    "mechanism branches when natural; never invent structure. "
                    "Use 주제별 Deep Dive with "
                    "주제 역할/Claim/Evidence/전망/플레이어/성장·저해/Watch. "
                    "Never emit per-topic 추후 보강. "
                    "미충족 보강 = only targets not filled from OPEN. "
                    "Korean body when sources are Korean. "
                    + HUMAN_CITE_RULE
                ),
            },
            {"role": "user", "content": prompt},
        ],
        model=model,
        temperature=0.25,
        label="fill",
        out_dir=out_dir,
    )

    content, stripped = strip_pillar_slots_from_filled(content)
    if stripped:
        log("fill: warning — stripped per-topic 추후 보강 from output")

    (out_dir / "06_filled_frame.md").write_text(content, encoding="utf-8")
    log(
        f"fill DONE opens_used={len(dossiers)} "
        f"slice_chars={sum(d['slice_chars'] for d in dossiers)}"
    )

    return content, {
        "plan": plan,
        "raw": plan_raw,
        "opens_used": len(dossiers),
        "slice_chars": sum(d["slice_chars"] for d in dossiers),
        "target_slots": target_slots,
        "stripped_pillar_slots": stripped,
        "slug_slices": slug_slices,
    }