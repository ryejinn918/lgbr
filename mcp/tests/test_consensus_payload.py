"""get_consensus MCP payload stays slim for background use."""

from __future__ import annotations

from lgbr_mcp.consensus import _consensus_payload, _run_summary


def test_payload_prefers_filled_frame_and_drops_ops_noise() -> None:
    run = {
        "id": "r1",
        "theme": "physical_ai",
        "state": "ended",
        "label": "ok",
        "question": "피지컬 AI, 지금 뭐 보면 돼?",
        "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": "2026-01-02T00:00:00+00:00",
        "criteria": {
            "thesis": "t",
            "cut_logic": "c",
            "pillar_sketch": ["a", "b"],
            "coverage_notes": "n",
            "until": "select",
            "resume_from": "doc",
            "core_count": 3,
            "core_max": 10,
        },
    }
    out = _consensus_payload(
        run=run,
        filled_frame="# 살 붙인 논지",
        consensus_frame="# 컨센서스 골격",
    )
    assert out["ok"] is True
    assert out["frame"] == "# 살 붙인 논지"
    assert "filled_frame" not in out
    assert "consensus_frame" not in out
    assert out["axes"] == {
        "thesis": "t",
        "cut_logic": "c",
        "pillar_sketch": ["a", "b"],
        "coverage_notes": "n",
    }
    assert out["run"] == {
        "id": "r1",
        "theme": "physical_ai",
        "question": "피지컬 AI, 지금 뭐 보면 돼?",
        "ended_at": "2026-01-02T00:00:00+00:00",
    }


def test_payload_falls_back_to_consensus_frame() -> None:
    run = {
        "id": "r2",
        "theme": "ai",
        "question": "q",
        "ended_at": "2026-01-02T00:00:00+00:00",
        "criteria": {"thesis": "t"},
    }
    out = _consensus_payload(
        run=run,
        filled_frame=None,
        consensus_frame="# 골격만",
    )
    assert out["frame"] == "# 골격만"


def test_run_summary_is_minimal() -> None:
    summary = _run_summary(
        {
            "id": "r3",
            "theme": "ai",
            "state": "ended",
            "label": "x",
            "question": "q",
            "started_at": "s",
            "ended_at": "e",
            "criteria": {"thesis": "dup", "until": "thesis"},
        }
    )
    assert summary == {
        "id": "r3",
        "theme": "ai",
        "question": "q",
        "ended_at": "e",
    }
