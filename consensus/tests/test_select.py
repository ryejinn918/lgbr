"""Unit tests for AI pack selection parsing (no LLM)."""

from __future__ import annotations

from consensus.select import (
    CORE_MAX,
    build_audit_cards,
    build_source_guardrail,
    parse_pack_selection,
    pool_themes_for,
    repair_source_guardrail_selection,
    select_system_prompt,
    source_guardrail_violations,
)


def test_select_system_requires_korean_and_omit_summary():
    for theme in (
        "ai",
        "datacenter",
        "macroeconomy",
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
        assert "[provider]" in prompt
        assert "published_at" in prompt
        assert "short_title" in prompt
        assert "fixed" in prompt.lower() or "Locked" in prompt or "locked" in prompt
        assert "Do NOT reinvent" in prompt or "Do NOT return pillar_sketch" in prompt


def test_pool_themes_ai_is_ai_only():
    assert pool_themes_for("ai") == ("ai",)
    assert pool_themes_for("datacenter") == ("datacenter",)
    assert pool_themes_for("macroeconomy") == ("macroeconomy",)
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
            "source": "Omdia",
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
    assert cards[0]["source"] == "omdia"
    assert len(cards[0]["framework_summary"]) <= 500


def test_sparse_sector_source_guardrail_requires_each_available_source():
    cards = [
        {"report_id": f"f-{i}", "source": "fnguide"} for i in range(2)
    ] + [
        {"report_id": f"k-{i}", "source": "kea"} for i in range(2)
    ] + [
        {"report_id": f"o-{i}", "source": "omdia"} for i in range(2)
    ]
    guardrail = build_source_guardrail(
        cards,
        theme="appliance",
        pillar_count=3,
        core_max=CORE_MAX,
    )

    assert guardrail is not None
    assert guardrail["available_sources"] == ["fnguide", "kea", "omdia"]
    assert guardrail["core_range"] == [3, 6]
    assert guardrail["selected_range"] == [6, 6]

    balanced_core = [("f-0", ""), ("k-0", ""), ("o-0", "")]
    balanced_biblio = [("f-1", ""), ("k-1", ""), ("o-1", "")]
    assert source_guardrail_violations(
        balanced_core,
        balanced_biblio,
        cards=cards,
        guardrail=guardrail,
    ) == []

    violations = source_guardrail_violations(
        [("f-0", ""), ("f-1", ""), ("k-0", "")],
        [("k-1", "")],
        cards=cards,
        guardrail=guardrail,
    )
    assert any("omdia" in violation for violation in violations)


def test_source_guardrail_is_limited_to_appliance_and_display():
    cards = [{"report_id": "f-0", "source": "fnguide"}]
    assert (
        build_source_guardrail(
            cards,
            theme="ai",
            pillar_count=3,
            core_max=CORE_MAX,
        )
        is None
    )


def test_source_guardrail_repair_adds_missing_source_and_count_floor():
    cards = [
        {"report_id": f"f-{i}", "source": "fnguide"} for i in range(2)
    ] + [
        {"report_id": f"k-{i}", "source": "kea"} for i in range(2)
    ] + [
        {"report_id": f"o-{i}", "source": "omdia"} for i in range(2)
    ]
    guardrail = build_source_guardrail(
        cards,
        theme="appliance",
        pillar_count=3,
        core_max=CORE_MAX,
    )

    core, biblio = repair_source_guardrail_selection(
        [("k-0", ""), ("o-0", ""), ("k-1", "")],
        [("o-1", "")],
        cards=cards,
        guardrail=guardrail,
    )

    assert len(core) == 3
    assert len(core) + len(biblio) == 6
    assert source_guardrail_violations(
        core,
        biblio,
        cards=cards,
        guardrail=guardrail,
    ) == []


def test_build_audit_cards_prefers_quality_short_title():
    pool = [
        {
            "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "title": "Chemicals Monthly Data-6 ~7월, 나프타 역래깅에 노출되다!",
            "provider": "KB투자증권",
            "theme": "petrochemical",
            "page_count": 20,
            "published_at": "2026-06-09",
            "quality_json": {
                "topic": "역래깅",
                "short_title": "6월 석화 마진",
                "framework_summary": "fw",
                "rationale": "r",
            },
        },
        {
            "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
            "title": "긴 원제목만 있는 보고서 제목입니다 추가",
            "provider": "삼성증권",
            "theme": "petrochemical",
            "page_count": 12,
            "published_at": None,
            "quality_json": {
                "topic": "x",
                "framework_summary": "fw",
                "rationale": "r",
            },
        },
    ]
    cards = build_audit_cards(pool)
    assert cards[0]["short_title"] == "6월 석화 마진"
    assert cards[0]["provider"] == "KB"
    assert cards[1]["short_title"].endswith("…") or len(cards[1]["short_title"]) <= 28
    assert "긴 원제목" in cards[1]["short_title"]


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
    locked = ["축 A", "축 B"]
    core, biblio, meta = parse_pack_selection(
        raw, allowed_ids=allowed, core_max=CORE_MAX, locked_pillars=locked
    )
    assert len(core) == CORE_MAX
    assert [c[0] for c in core] == [f"id-{i}" for i in range(CORE_MAX)]
    assert biblio == [("id-12", "b")]
    assert meta["pillar_sketch"] == locked
    assert meta["coverage_notes"] == "notes"


def test_parse_pack_empty_core_allowed_for_parser():
    core, biblio, _meta = parse_pack_selection(
        {"core": [], "bibliography": []},
        allowed_ids={"a"},
        core_max=10,
    )
    assert core == []
    assert biblio == []
