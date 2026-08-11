"""Unit tests for Nikkei RSS date parsing."""

from __future__ import annotations

from datetime import datetime, timezone

from crawler.sources.nikkei_feed import _parse_dc_date


def test_parse_dc_date_with_offset() -> None:
    dt = _parse_dc_date("2026-08-11T05:00:00+09:00")
    assert dt == datetime(2026, 8, 10, 20, 0, 0, tzinfo=timezone.utc)


def test_parse_dc_date_naive_is_jst() -> None:
    dt = _parse_dc_date("2026-08-10T21:35:34")
    assert dt == datetime(2026, 8, 10, 12, 35, 34, tzinfo=timezone.utc)


def test_parse_dc_date_zulu() -> None:
    dt = _parse_dc_date("2026-08-10T12:35:34Z")
    assert dt == datetime(2026, 8, 10, 12, 35, 34, tzinfo=timezone.utc)


def test_parse_dc_date_empty() -> None:
    assert _parse_dc_date(None) is None
    assert _parse_dc_date("") is None
    assert _parse_dc_date("not-a-date") is None
