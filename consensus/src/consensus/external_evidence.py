"""Load AI-classified external evidence for the final Consensus prompts."""

from __future__ import annotations

import json
from typing import Any

from consensus.db import connect


def _summary(quality_json: Any) -> str:
    if not isinstance(quality_json, dict):
        return ""
    for key in ("summary", "framework_summary", "rationale", "abstract"):
        value = str(quality_json.get(key) or "").strip()
        if value:
            return value[:1200]
    return ""


def load_external_evidence(run_id: str) -> list[dict[str, Any]]:
    """Return linked external reports with compact summaries and AI relations."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT x.axis_index, x.axis_label, x.report_id::text AS report_id,
                   x.relation, x.ai_reason, x.ai_confidence, x.review_state,
                   r.source, r.title, r.published_at,
                   r.attrs->>'provider' AS provider, r.quality_json
            FROM consensus_axis_external_docs x
            JOIN reports r ON r.id = x.report_id
            WHERE x.run_id = %s::uuid
              AND x.review_state IN ('ai_suggested', 'approved', 'manual')
            ORDER BY x.axis_index, x.ai_confidence DESC NULLS LAST,
                     r.published_at DESC NULLS LAST
            """,
            (run_id,),
        )
        rows = cur.fetchall()

    evidence: list[dict[str, Any]] = []
    for row in rows:
        summary = _summary(row.get("quality_json"))
        if not summary:
            continue
        evidence.append(
            {
                "axis_index": int(row["axis_index"]),
                "axis_label": str(row["axis_label"] or ""),
                "report_id": str(row["report_id"]),
                "relation": str(row["relation"] or "supplement"),
                "ai_reason": str(row["ai_reason"] or ""),
                "ai_confidence": float(row["ai_confidence"])
                if row["ai_confidence"] is not None
                else None,
                "source": str(row["provider"] or row["source"] or ""),
                "title": str(row["title"] or ""),
                "published_at": str(row["published_at"] or ""),
                "summary": summary,
            }
        )
    return evidence


def format_external_evidence(evidence: list[dict[str, Any]]) -> str:
    """Format a bounded prompt block while keeping roles explicit."""
    if not evidence:
        return "(No AI-classified external evidence is attached.)"
    rows: list[str] = []
    for item in evidence[:60]:
        rows.append(
            "- axis={axis}\n"
            "  relation={relation}\n"
            "  source={source}; title={title}; published_at={date}\n"
            "  AI reason={reason}\n"
            "  summary={summary}".format(
                axis=item["axis_label"],
                relation=item["relation"],
                source=item["source"],
                title=item["title"],
                date=item["published_at"],
                reason=item["ai_reason"] or "not provided",
                summary=item["summary"],
            )
        )
    return "\n".join(rows)
