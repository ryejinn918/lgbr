"""Unit tests for AI pack selection parsing (no LLM)."""

from __future__ import annotations

from consensus.select import (
    CORE_MAX,
    build_audit_cards,
    parse_pack_selection,
    pool_themes_for,
    select_system_prompt,
)


def test_select_system_requires_korean_and_omit_summary():
    for theme in (
        "ai",
        "datacenter",
        "physical_ai",
        "appliance",
        "display",
        "automotive",
        "petrochemical",
    ):
        prompt = select_system_prompt(theme)
        assert "Korean" in prompt
        assert "Omit summary" in prompt
        assert "omitted[]" in prompt
        assert "humans" in prompt
        assert "(provider)" in prompt
        assert "published_at" in prompt
        assert "short_title alone" in prompt


def test_pool_themes_ai_includes_datacenter():
    assert pool_themes_for("ai") == ("ai", "datacenter")
    assert pool_themes_for("datacenter") == ("datacenter",)
    assert pool_themes_for("physical_ai") == ("physical_ai",)
    assert pool_themes_for("appliance") == ("appliance",)
    assert pool_themes_for("display") == ("display",)
    assert pool_themes_for("automotive") == ("automotive",)
    assert pool_themes_for("petrochemical") == ("petrochemical",)


def test_build_audit_cards_clips_quality_json():
    pool = [
        {
            "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "title": "T",
            "theme": "ai",
            "page_count": 10,
            "published_at": None,
            "quality_json": {
                "topic": "x",
                "framework_summary": "f" * 600,
                "rationale": "r",
            },
        }
    ]
    cards = build_audit_cards(pool)
    assert len(cards) == 1
    assert cards[0]["report_id"].startswith("aaaa")
    assert len(cards[0]["framework_summary"]) <= 500


def test_parse_pack_selection_caps_core_and_dedupes():
    allowed = {f"id-{i}" for i in range(15)}
    raw = {
        "core": [{"report_id": f"id-{i}", "why": f"w{i}"} for i in range(12)],
        "bibliography": [
            {"report_id": "id-0", "why": "dup"},
            {"report_id": "id-12", "why": "b"},
            {"report_id": "missing", "why": "x"},
        ],
        "coverage_notes": "notes",
        "pillar_sketch": ["power", "network", ""],
    }
    core, biblio, meta = parse_pack_selection(
        raw, allowed_ids=allowed, core_max=CORE_MAX
    )
    assert len(core) == CORE_MAX
    assert [c[0] for c in core] == [f"id-{i}" for i in range(CORE_MAX)]
    assert biblio == [("id-12", "b")]
    assert meta["pillar_sketch"] == ["power", "network"]
    assert meta["coverage_notes"] == "notes"


def test_parse_pack_empty_core_allowed_for_parser():
    core, biblio, _meta = parse_pack_selection(
        {"core": [], "bibliography": []},
        allowed_ids={"a"},
        core_max=10,
    )
    assert core == []
    assert biblio == []
