"""Signed PDF URL helpers."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from lgbr_mcp.signed_urls import sign_report_pdf_url, verify_report_signature


def test_sign_and_verify_roundtrip() -> None:
    rid = "fdcf60d0-e383-4720-99f1-708b8bd1705e"
    url = sign_report_pdf_url(rid, ttl_seconds=120)
    assert "/files/reports/" + rid in url
    qs = parse_qs(urlparse(url).query)
    assert verify_report_signature(rid, qs["exp"][0], qs["sig"][0])
    assert not verify_report_signature(rid, qs["exp"][0], "0" * 64)
    assert not verify_report_signature(rid, "1", qs["sig"][0])
