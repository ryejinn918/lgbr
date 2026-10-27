"""Sector-specific evidence eligibility rules for consensus input pools."""

from __future__ import annotations

from typing import Any


SPARSE_EVIDENCE_THEMES = frozenset({"appliance", "display"})

EVIDENCE_LIMITATION_UI_NOTE = (
    "산업 전체를 다루는 자료가 제한적입니다. "
    "확보된 기업·제품 중심 자료를 보완적으로 활용합니다."
)


def quality_json(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("quality_json")
    return value if isinstance(value, dict) else {}


def is_sparse_theme(theme: str) -> bool:
    return str(theme or "").strip().lower() in SPARSE_EVIDENCE_THEMES


def is_evidence_eligible(row: dict[str, Any], *, theme: str) -> bool:
    if row.get("quality_pass") is True:
        return True
    return is_sparse_theme(theme) and quality_json(row).get("evidence_status") == "insufficient"


def evidence_status(row: dict[str, Any]) -> str | None:
    value = quality_json(row).get("evidence_status")
    return str(value) if value else None



def evidence_assessment(rows: list[dict[str, Any]], *, theme: str) -> dict[str, Any]:
    """Assess whether a sparse sector needs a data-coverage caveat."""
    if not is_sparse_theme(theme):
        return {
            "notice": False,
            "ui_note": None,
            "report_note": None,
            "reason_codes": [],
            "quality_pass_count": sum(1 for r in rows if r.get("quality_pass") is True),
            "industry_wide_count": 0,
            "supplemental_count": 0,
            "mostly_company_product_focused": False,
        }

    eligible = [r for r in rows if is_evidence_eligible(r, theme=theme)]
    quality_pass_count = sum(1 for r in rows if r.get("quality_pass") is True)
    industry_wide_count = sum(
        1
        for r in rows
        if r.get("quality_pass") is True
        and quality_json(r).get("has_broad_sector_coverage") is True
    )
    supplemental_count = sum(1 for r in eligible if r.get("quality_pass") is not True)
    mostly_company_product_focused = bool(eligible) and (
        len(eligible) - industry_wide_count > len(eligible) / 2
    )
    reason_codes: list[str] = []
    if quality_pass_count == 0:
        reason_codes.append("no_quality_pass")
    if quality_pass_count > 0 and industry_wide_count < 2:
        reason_codes.append("fewer_than_two_industry_wide_reports")
    if mostly_company_product_focused:
        reason_codes.append("mostly_company_product_focused")

    notice = bool(reason_codes)
    sector = "가전" if theme == "appliance" else "디스플레이"
    report_note = (
        f"본 분석은 FnGuide 및 확보 가능한 보완 자료를 기준으로 작성되었습니다. "
        f"분석 대상 기간 내 {sector} 산업 전체를 직접 다루는 보고서가 제한적이어서 "
        "일부 기업·제품 중심 자료를 함께 활용했습니다."
        if notice
        else None
    )
    return {
        "notice": notice,
        "ui_note": EVIDENCE_LIMITATION_UI_NOTE if notice else None,
        "report_note": report_note,
        "reason_codes": reason_codes,
        "quality_pass_count": quality_pass_count,
        "industry_wide_count": industry_wide_count,
        "supplemental_count": supplemental_count,
        "mostly_company_product_focused": mostly_company_product_focused,
    }