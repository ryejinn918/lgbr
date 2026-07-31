"""Unit tests for BCG HTTP list/detail/pdf helpers."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from crawler.sources.bcg_http import (
    BcgBlockedError,
    BcgCaptureError,
    download_pdf,
    fetch_list_items,
    find_pdf_url,
    parse_list_html,
    parse_publish_date_from_html,
)


LIST_HTML = """
<html><body>
<article class="card">
  <span class="date">July 15, 2026</span>
  <a href="/publications/2026/building-business-value-with-ai-investment">
    Building Business Value with AI Investment Strategy
  </a>
</article>
<article>
  <a href="https://www.bcg.com/publications/2025/supply-chain-resilience-playbook">
    Supply Chain Resilience Playbook for Global Leaders
  </a>
  <p>Published December 1, 2025</p>
</article>
<a href="/industries/automotive/overview">Not a publication</a>
</body></html>
"""

DETAIL_HTML = """
<html><body>
<script type="application/ld+json">
{"datePublished":"2026-07-15"}
</script>
<a href="https://web-assets.bcg.com/pdf-src/building-business-value.pdf"
   aria-label="Download PDF">Download</a>
<a href="/media/transcript.pdf">Transcript</a>
</body></html>
"""

DENIED_HTML = """
<html><body><h1>Access Denied</h1>
<p>You don't have permission. Reference #18.abc</p>
</body></html>
"""


def test_parse_list_html_extracts_cards() -> None:
    items = parse_list_html(
        LIST_HTML, list_url="https://www.bcg.com/publications"
    )
    assert len(items) == 2
    assert items[0].source_key == "2026/building-business-value-with-ai-investment"
    assert "Business Value" in items[0].title
    assert items[0].published_at == date(2026, 7, 15)
    assert items[1].source_key == "2025/supply-chain-resilience-playbook"
    assert items[1].published_at == date(2025, 12, 1)


def test_parse_list_html_rejects_denied() -> None:
    with pytest.raises(BcgBlockedError):
        parse_list_html(DENIED_HTML, list_url="https://www.bcg.com/publications")


def test_fetch_list_items_rejects_non_allowlisted() -> None:
    with pytest.raises(BcgCaptureError, match="not allowlisted"):
        fetch_list_items(
            "https://www.bcg.com/industries/made-up",
            profile="report",
        )


def test_find_pdf_url_prefers_web_assets() -> None:
    pdf = find_pdf_url(
        DETAIL_HTML,
        page_url="https://www.bcg.com/publications/2026/building-business-value-with-ai-investment",
    )
    assert pdf is not None
    assert "web-assets.bcg.com" in pdf
    assert "transcript" not in pdf.lower()


def test_parse_publish_date_from_html() -> None:
    assert parse_publish_date_from_html(DETAIL_HTML) == date(2026, 7, 15)


def test_download_pdf_writes_valid_magic(tmp_path: Path) -> None:
    dest = tmp_path / "out.pdf"
    sess = MagicMock()
    with patch(
        "crawler.sources.bcg_http.get_bytes",
        return_value=b"%PDF-1.4 fake content",
    ):
        n = download_pdf(
            "https://web-assets.bcg.com/x.pdf",
            dest,
            session=sess,
            referer="https://www.bcg.com/publications/2026/x",
        )
    assert n == len(b"%PDF-1.4 fake content")
    assert dest.read_bytes().startswith(b"%PDF")


def test_download_pdf_rejects_non_pdf(tmp_path: Path) -> None:
    with patch(
        "crawler.sources.bcg_http.get_bytes",
        return_value=b"<html>not a pdf</html>",
    ):
        with pytest.raises(BcgCaptureError, match="not a PDF"):
            download_pdf("https://web-assets.bcg.com/x.pdf", tmp_path / "bad.pdf")


def test_download_pdf_rejects_denied(tmp_path: Path) -> None:
    with patch(
        "crawler.sources.bcg_http.get_bytes",
        return_value=b"<html>Access Denied Reference #1</html>",
    ):
        with pytest.raises(BcgBlockedError):
            download_pdf("https://web-assets.bcg.com/x.pdf", tmp_path / "bad.pdf")
