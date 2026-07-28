"""awaiting → continue criteria flags (no DB)."""

from __future__ import annotations


def apply_continue_criteria(
    criteria: dict,
    *,
    thesis: str | None,
    cut_logic: str | None,
    pillar_sketch: list[str] | None,
    until: str | None,
) -> dict:
    """Mirror api continue_run criteria merge (unit-testable)."""
    out = dict(criteria)
    if thesis is not None:
        out["thesis"] = str(thesis).strip()
    if cut_logic is not None:
        out["cut_logic"] = str(cut_logic).strip()
    if pillar_sketch is not None:
        out["pillar_sketch"] = [str(p).strip() for p in pillar_sketch if str(p).strip()]
    out["resume_from"] = "select"
    if until == "select":
        out["until"] = "select"
    else:
        out.pop("until", None)
    return out


def test_continue_select_only_keeps_until():
    base = {
        "theme": "automotive",
        "until": "thesis",
        "thesis": "old",
        "cut_logic": "old",
        "pillar_sketch": ["a", "b"],
    }
    out = apply_continue_criteria(
        base,
        thesis="수정된 긴장",
        cut_logic="이유",
        pillar_sketch=["축1", "축2", "축3"],
        until="select",
    )
    assert out["resume_from"] == "select"
    assert out["until"] == "select"
    assert out["thesis"] == "수정된 긴장"
    assert out["pillar_sketch"] == ["축1", "축2", "축3"]


def test_continue_full_clears_until():
    base = {"until": "thesis", "thesis": "t", "pillar_sketch": ["a", "b"]}
    out = apply_continue_criteria(
        base,
        thesis="t",
        cut_logic="c",
        pillar_sketch=["a", "b"],
        until=None,
    )
    assert out["resume_from"] == "select"
    assert "until" not in out


def test_resume_doc_clears_until():
    base = {
        "until": "select",
        "thesis": "t",
        "pillar_sketch": ["a", "b"],
        "core_count": 10,
    }
    out = dict(base)
    out["resume_from"] = "doc"
    out.pop("until", None)
    assert out["resume_from"] == "doc"
    assert "until" not in out
    assert out["thesis"] == "t"
