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
    *,
    run_id: str,
    axis_index: int,
    axis_label: str,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    data = list_candidates(
        run_id=run_id,
        axis_index=axis_index,
    )

    candidates = [
        item
        for item in data.get("items", [])
        if _summary(item)
    ]

    if not candidates:
        return {
            "ok": True,
            "status": "completed",
            "run_id": run_id,
            "axis_index": axis_index,
            "items": [],
            "message": (
                "분석 가능한 외부 보고서가 없습니다. "
                "외부 보고서의 품질 요약이 아직 없거나 관련 자료가 부족합니다."
            ),
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

    prompt = """
분석 축과 외부 보고서 요약을 비교해 관련 보고서만 추천하세요.

분석 축:
{axis_label}

각 추천은 다음 중 하나로 분류하세요.

- corroboration: FnGuide 관점을 지지
- dissent: FnGuide 관점과 상반
- supplement: 추가 정보로 보완

분석 축과 관련 없는 보고서는 제외하세요.
근거가 부족하면 추천하지 마세요.
JSON 객체만 반환하세요.

반환 형식:
{{
  "items": [
    {{
      "report_id": "...",
      "relation": "corroboration|dissent|supplement",
      "confidence": 0.0,
      "reason": "..."
    }}
  ]
}}

외부 보고서:
{cards}
""".format(
        axis_label=axis_label,
        cards=json.dumps(cards, ensure_ascii=False),
    )

    raw, _ = await chat(
        [
            {
                "role": "system",
                "content": (
                    "외부 보고서와 분석 축의 관계를 보수적으로 분류하는 "
                    "검토 보조 AI입니다. 근거 없는 추천은 하지 마세요."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        model=model,
        temperature=0.1,
        label=f"external-review-axis-{axis_index}",
    )

    parsed = parse_json(raw)

    if not isinstance(parsed, dict):
        parsed = {}

    by_id = {
        str(item["report_id"]): item
        for item in candidates
    }

    saved: list[dict[str, Any]] = []

    with connect() as conn, conn.cursor() as cur:
        for suggestion in parsed.get("items") or []:
            if not isinstance(suggestion, dict):
                continue

            report_id = str(
                suggestion.get("report_id") or ""
            ).strip()

            relation = str(
                suggestion.get("relation") or ""
            ).strip().lower()

            if report_id not in by_id:
                continue

            if relation not in RELATIONS:
                continue

            try:
                confidence = max(
                    0.0,
                    min(
                        1.0,
                        float(
                            suggestion.get("confidence") or 0
                        ),
                    ),
                )
            except (TypeError, ValueError):
                confidence = 0.0

            reason = str(
                suggestion.get("reason") or ""
            ).strip()[:2000]

            cur.execute(
                """
                INSERT INTO consensus_axis_external_docs
                    (
                        run_id,
                        axis_index,
                        axis_label,
                        report_id,
                        relation,
                        select_reason,
                        ai_confidence,
                        ai_reason,
                        review_state
                    )
                VALUES (
                    %s::uuid,
                    %s,
                    %s,
                    %s::uuid,
                    %s,
                    %s,
                    %s,
                    %s,
                    'ai_suggested'
                )
                ON CONFLICT (
                    run_id,
                    axis_index,
                    report_id
                )
                DO UPDATE SET
                    axis_label = EXCLUDED.axis_label,
                    relation = EXCLUDED.relation,
                    select_reason = EXCLUDED.select_reason,
                    ai_confidence = EXCLUDED.ai_confidence,
                    ai_reason = EXCLUDED.ai_reason,
                    review_state = 'ai_suggested',
                    updated_at = now()
                RETURNING
                    report_id::text AS report_id,
                    relation,
                    ai_confidence,
                    ai_reason,
                    review_state
                """,
                (
                    run_id,
                    axis_index,
                    axis_label.strip(),
                    report_id,
                    relation,
                    reason,
                    confidence,
                    reason,
                ),
            )

            row = cur.fetchone()

            if row:
                saved.append(_json_row(row))

        conn.commit()

    if saved:
        message = (
            "외부 자료 분석이 완료되었습니다. "
            f"{len(saved)}건의 추천 자료를 확인할 수 있습니다."
        )
    else:
        message = (
            "외부 자료 분석은 완료되었지만, "
            "현재 분석 축과 연결할 외부 자료가 없습니다."
        )

    return {
        "ok": True,
        "status": "completed",
        "run_id": run_id,
        "axis_index": axis_index,
        "items": saved,
        "message": message,
    }