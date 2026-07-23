"""Fill locked consensus frame by reopening report slices."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from consensus.llm import DEFAULT_MODEL, chat, log, parse_json


def _keyword_hits(text: str, queries: list[str], window: int = 1600, max_hits: int = 6) -> str:
    if not queries:
        return text[: min(len(text), window * 2)]
    chunks: list[str] = []
    lowered = text.lower()
    for q in queries:
        q = (q or "").strip()
        if not q:
            continue
        idx = lowered.find(q.lower())
        if idx < 0:
            continue
        start = max(0, idx - window // 3)
        end = min(len(text), idx + len(q) + window * 2 // 3)
        chunks.append(f"[hit q={q} @char={idx}]\n{text[start:end]}")
        if len(chunks) >= max_hits:
            break
    if not chunks:
        return f"[no keyword hits] queries={queries}\n" + text[: min(len(text), window)]
    return "\n\n----\n\n".join(chunks)


def fill_frame(
    frame: str,
    slug_to_dir: dict[str, Path],
    *,
    question: str,
    out_dir: Path,
    model: str = DEFAULT_MODEL,
) -> tuple[str, dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    slug_list = sorted(slug_to_dir)
    plan_raw, _ = chat(
        [
            {
                "role": "system",
                "content": "Output JSON only. Plan body opens to fill frame slots.",
            },
            {
                "role": "user",
                "content": (
                    f"질문: {question}\n\n컨센서스 프레임:\n{frame}\n\n"
                    "프레임의 '나중에 채울 슬롯'과 '본문 재조사 우선순위'를 채우기 위해 "
                    "각 리포트 슬라이스에서 찾을 키워드를 정해라.\n"
                    "중요: queries는 문장/긴 구절 금지. 본문에 그대로 있을 짧은 고유명사·키워드만.\n"
                    "JSON:\n"
                    '{"opens":[{"slug":"...","slice_id":"s01|front_matter|whole",'
                    '"queries":["RMAC","Atlas"],"slot":"칸 이름/슬롯","why":"..."}]}\n'
                    f"slug 후보: {slug_list}\n"
                    "각 slug의 slice_id는 front_matter/s01/s02/whole 중 그럴듯한 것을 쓰고, "
                    "없으면 whole를 써라.\n"
                    "슬롯을 커버할 만큼 opens를 잡아라."
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
        slug = (op.get("slug") or "").strip()
        slice_id = (op.get("slice_id") or "whole").strip()
        queries = op.get("queries") or []
        doc_dir = slug_to_dir.get(slug)
        if doc_dir is None:
            for k, d in slug_to_dir.items():
                if slug and (slug in k or k in slug):
                    doc_dir = d
                    slug = k
                    break
        if doc_dir is None:
            log(f"  skip open {i}: unknown slug={op.get('slug')}")
            continue

        slice_path = doc_dir / "01_slices" / f"{slice_id}.txt"
        if not slice_path.is_file():
            candidates = sorted((doc_dir / "01_slices").glob("*.txt"))
            if not candidates:
                log(f"  skip open {i}: no slices in {slug}")
                continue
            whole = doc_dir / "01_slices" / "whole.txt"
            slice_path = whole if whole.is_file() else candidates[0]
            slice_id = slice_path.stem
            log(f"  open {i}: slice fallback → {slice_id}")

        text = slice_path.read_text(encoding="utf-8")
        body = _keyword_hits(text, list(queries))
        hit_n = 0 if body.startswith("[no keyword hits]") else body.count("[hit ")
        log(f"  open [{i}] {slug}/{slice_id} queries={queries} hits={hit_n}")
        dossiers.append(
            {
                "slug": slug,
                "slice_id": slice_id,
                "slot": op.get("slot"),
                "why": op.get("why"),
                "queries": queries,
                "body": body,
                "hits": hit_n,
            }
        )
        (out_dir / f"05_open_{i}.txt").write_text(body, encoding="utf-8")

    usable = [d for d in dossiers if d["hits"] > 0 or d["body"]]
    if not usable:
        raise RuntimeError("fill: no body opens succeeded")

    with_hits = [d for d in usable if d["hits"] > 0]
    chosen = with_hits if with_hits else usable
    if not with_hits:
        log("fill: warning — no keyword hits; using slice excerpts")

    dossier_txt = "\n\n========\n\n".join(
        f"### OPEN {d['slug']}/{d['slice_id']} | slot={d['slot']} | why={d['why']}\n{d['body']}"
        for d in chosen
    )
    prompt = f"""잠긴 컨센서스 큰 틀은 유지하고, 아래 OPEN 조각에 **실제로 나온 문장·수치만**으로 칸을 두껍게 채워라.
큰 칸 제목/지붕을 바꾸지 마라.
OPEN에 없는 수치·기업 사실·가격을 절대 만들지 마라. 없으면 '아직 빈 슬롯'에 넣어라.
출처로 slug를 근거에 붙여라.

질문: {question}

## 잠긴 큰 틀
{frame}

## 본문에서 연 조각
{dossier_txt}

출력:
# 보강된 프레임 (큰 틀 유지)

## 지붕
(틀과 동일 취지)

## 칸별 보강
### 1. (기존 칸 제목)
- **주장**
- **근거(수치·시점·출처 slug)**
- **추적**
(두껍게)

## 아직 빈 슬롯 (웹/다른 소스로 넘길 것)
- 문헌에서 못 채운 항목만. 각 항목에 다음에 쓸 질의 후보 한 줄.

## 참고 리포트
...
"""
    content, _ = chat(
        [
            {
                "role": "system",
                "content": (
                    "Enrich a locked consensus frame with opened report bodies. "
                    "Keep roof/pillars. Grow density. Korean. No invented facts."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        model=model,
        temperature=0.25,
        label="fill",
        out_dir=out_dir,
    )
    (out_dir / "06_filled_frame.md").write_text(content, encoding="utf-8")
    log("fill DONE")
    return content, {"plan": plan, "raw": plan_raw, "opens_used": len(chosen)}
