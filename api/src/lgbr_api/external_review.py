"""AI recommendations for attaching external reports to Consensus axes."""

from __future__ import annotations

import json
from typing import Any

from consensus.llm import DEFAULT_MODEL, chat, parse_json
from lgbr_api.db import connect
from lgbr_api.external_links import _json_row, list_candidates

RELATIONS = {"corroboration", "dissent", "supplement"}


def _summary(item: dict[str, Any]) -> str:
    qj = item.get("quality_json")
    if isinstance(qj, dict):
        for key in ("summary", "framework_summary", "rationale", "abstract"):
            value = str(qj.get(key) or "").strip()
            if value:
                return value[:1200]
    return ""


async def recommend_external_docs(
    *, run_id: str, axis_index: int, axis_label: str, model: str = DEFAULT_MODEL
) -> dict[str, Any]:
    data = list_candidates(run_id=run_id, axis_index=axis_index)
    candidates = [item for item in data["items"] if _summary(item)]
    if not candidates:
        return {
            "ok": True,
            "run_id": run_id,
            "axis_index": axis_index,
            "items": [],
            "message": "quality summaryê°€ ìžˆëŠ” ì™¸ë¶€ ë³´ê³ ì„œ í›„ë³´ê°€ ì—†ìŠµë‹ˆë‹¤.",
        }

    cards = [
        {
            "report_id": item["report_id"],
            "source": item.get("source"),
            "title": item.get("title"),
            "published_at": str(item.get("published_at") or ""),
            "summary": _summary(item),
        }
        for item in candidates[:20]
    ]
    prompt = """ë¶„ì„ ì¶•ê³¼ ì™¸ë¶€ ë³´ê³ ì„œ ìš”ì•½ì„ ë¹„êµí•´ ê´€ë ¨ ë³´ê³ ì„œë§Œ ì¶”ì²œí•˜ì„¸ìš”.

ë¶„ì„ ì¶•: {axis_label}

ê° ì¶”ì²œì€ ë‹¤ìŒ ì¤‘ í•˜ë‚˜ë¡œ ë¶„ë¥˜í•©ë‹ˆë‹¤.
- corroboration: FnGuide ê´€ì ì„ ì§€ì§€
- dissent: FnGuide ê´€ì ê³¼ ìƒë°˜
- supplement: ì¶”ê°€ ì •ë³´ë¡œ ë³´ì™„

ê´€ë ¨ ì—†ëŠ” ë³´ê³ ì„œëŠ” ì œì™¸í•˜ì„¸ìš”. JSON ê°ì²´ë§Œ ë°˜í™˜í•˜ì„¸ìš”.
í˜•ì‹:
{{"items":[{{"report_id":"...","relation":"corroboration|dissent|supplement","confidence":0.0,"reason":"..."}}]}}

ìžë£Œ:
{cards}
""".format(axis_label=axis_label, cards=json.dumps(cards, ensure_ascii=False))
    raw, _ = await chat(
        [
            {
                "role": "system",
                "content": "ì™¸ë¶€ ë³´ê³ ì„œì™€ ë¶„ì„ ì¶•ì˜ ê´€ê³„ë¥¼ ë³´ìˆ˜ì ìœ¼ë¡œ ë¶„ë¥˜í•˜ëŠ” ê²€í†  ë³´ì¡° AIìž…ë‹ˆë‹¤. ê·¼ê±° ì—†ëŠ” ì¶”ì²œì€ í•˜ì§€ ë§ˆì„¸ìš”.",
            },
            {"role": "user", "content": prompt},
        ],
        model=model,
        temperature=0.1,
        label=f"external-review-axis-{axis_index}",
    )
    parsed = parse_json(raw)
    by_id = {str(item["report_id"]): item for item in candidates}
    saved: list[dict[str, Any]] = []
    with connect() as conn, conn.cursor() as cur:
        for suggestion in parsed.get("items") or []:
            report_id = str(suggestion.get("report_id") or "")
            relation = str(suggestion.get("relation") or "").strip().lower()
            if report_id not in by_id or relation not in RELATIONS:
                continue
            try:
                confidence = max(0.0, min(1.0, float(suggestion.get("confidence") or 0)))
            except (TypeError, ValueError):
                confidence = 0.0
            reason = str(suggestion.get("reason") or "").strip()[:2000]
            cur.execute(
                """
                INSERT INTO consensus_axis_external_docs
                    (run_id, axis_index, axis_label, report_id, relation,
                     select_reason, ai_confidence, ai_reason, review_state)
                VALUES (%s::uuid, %s, %s, %s::uuid, %s, %s, %s, %s, 'ai_suggested')
                ON CONFLICT (run_id, axis_index, report_id) DO UPDATE SET
                    axis_label = EXCLUDED.axis_label,
                    relation = EXCLUDED.relation,
                    select_reason = EXCLUDED.select_reason,
                    ai_confidence = EXCLUDED.ai_confidence,
                    ai_reason = EXCLUDED.ai_reason,
                    review_state = 'ai_suggested',
                    updated_at = now()
                RETURNING report_id::text AS report_id, relation,
                          ai_confidence, ai_reason, review_state
                """,
                (run_id, axis_index, axis_label.strip(), report_id, relation, reason, confidence, reason),
            )
            saved.append(_json_row(cur.fetchone()))
        conn.commit()
    return {"ok": True, "run_id": run_id, "axis_index": axis_index, "items": saved}

