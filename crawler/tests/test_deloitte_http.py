"""Unit tests for Deloitte PDF href selection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from crawler.sources.deloitte_http import download_pdf, find_pdf_url


PAGE = "https://www.deloitte.com/us/en/insights/topics/economy/example.html"


def test_find_pdf_url_prefers_deloitte_insights_dam() -> None:
    html = """
    <a href="https://www.bls.gov/news.release/pdf/tenure.pdf">BLS</a>
    <a href="/content/dam/insights/articles/2026/us123/pdf/DI_Report.pdf"
       aria-label="Download PDF">PDF</a>
    """
    assert (
        find_pdf_url(html, page_url=PAGE)
        == "https://www.deloitte.com/content/dam/insights/articles/2026/us123/pdf/DI_Report.pdf"
    )


def test_find_pdf_url_ignores_third_party_only() -> None:
    html = """
    <a href="https://www.federalreserve.gov/releases/z1/20260319/z1.pdf">Fed</a>
    <a href="https://www.oecd.org/content/dam/report.pdf">OECD</a>
    """
    assert find_pdf_url(html, page_url=PAGE) is None


def test_find_pdf_url_allows_deloitte_subdomain() -> None:
    html = '<a href="https://www2.deloitte.com/content/dam/foo/bar.pdf">PDF</a>'
    assert (
        find_pdf_url(html, page_url=PAGE)
        == "https://www2.deloitte.com/content/dam/foo/bar.pdf"
    )


def test_download_pdf_refuses_non_deloitte_host(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="non-Deloitte"):
        download_pdf(
            "https://www.bls.gov/news.release/pdf/tenure.pdf",
            tmp_path / "x.pdf",
        )


def test_download_pdf_refuses_tiny_payload(tmp_path: Path) -> None:
    sess = MagicMock()
    with patch("crawler.sources.deloitte_http.get_bytes", return_value=b"%PDF-tiny"):
        with pytest.raises(RuntimeError, match="too small"):
            download_pdf(
                "https://www.deloitte.com/content/dam/a.pdf",
                tmp_path / "x.pdf",
                session=sess,
            )
