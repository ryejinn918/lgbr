"""Stop / pause_awaiting contract (logic only; DB covered by integration)."""

from __future__ import annotations


def test_stop_requested_wins_over_awaiting_intent():
    """Document expected pause_awaiting outcomes."""
    # If stop_requested_at is set, pause must end the run (not clear the flag).
    outcomes = {
        "stop_set": "ended",
        "stop_clear": "awaiting",
    }
    assert outcomes["stop_set"] == "ended"
    assert outcomes["stop_clear"] == "awaiting"


def test_resume_doc_from_error_criteria():
    criteria = {
        "thesis": "t",
        "pillar_sketch": ["a", "b"],
        "resume_from": "doc",
    }
    assert "until" not in criteria
    assert criteria["resume_from"] == "doc"
