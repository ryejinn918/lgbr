"""KPMG profile allowlist guards."""

from __future__ import annotations

import pytest

from crawler.sources.kpmg_http import get_profile


def test_report_profile_includes_hub_browse() -> None:
    prof = get_profile("report")
    assert "*" in prof.queries
    assert "report" in prof.queries


def test_ai_profile_includes_talent() -> None:
    prof = get_profile("ai")
    assert "AI" in prof.queries
    assert "talent" in prof.queries


def test_unknown_profile_raises() -> None:
    with pytest.raises(ValueError, match="unknown KPMG profile"):
        get_profile("not-a-theme")
