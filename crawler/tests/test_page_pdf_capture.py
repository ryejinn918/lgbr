"""Unit tests for page.pdf capture gates (no browser)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from crawler.sources.page_pdf_capture import (
    DEFAULT_MIN_PDF_BYTES,
    DEFAULT_MIN_PDF_TEXT_CHARS,
    EmptyPagePdfError,
    _ensure_body_painted,
    capture_url_as_pdf,
    pdf_extract_char_count,
)


def test_pdf_extract_char_count_missing_file(tmp_path: Path):
    assert pdf_extract_char_count(tmp_path / "nope.pdf") == 0


def test_pdf_extract_char_count_uses_pdftotext(tmp_path: Path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    fake = MagicMock(
        return_value=MagicMock(stdout="  hello world  \n\n", stderr="", returncode=0)
    )
    with (
        patch("crawler.sources.page_pdf_capture.shutil.which", return_value="/bin/pdftotext"),
        patch("crawler.sources.page_pdf_capture.subprocess.run", fake),
    ):
        assert pdf_extract_char_count(pdf) == len("hello world")
    args = fake.call_args[0][0]
    assert args[:4] == ["pdftotext", "-f", "1", "-l"]


def test_capture_url_as_pdf_rejects_thin_text(tmp_path: Path):
    page = MagicMock()
    page.evaluate.return_value = {"body_len": 5000, "title": "T"}
    dest = tmp_path / "out.pdf"

    def fake_pdf(*, path, **_kwargs):
        Path(path).write_bytes(b"%PDF" + b"x" * (DEFAULT_MIN_PDF_BYTES + 10))

    page.pdf.side_effect = fake_pdf

    with (
        patch(
            "crawler.sources.page_pdf_capture._dismiss_cookie_banner",
            return_value=None,
        ),
        patch(
            "crawler.sources.page_pdf_capture.pdf_extract_char_count",
            return_value=DEFAULT_MIN_PDF_TEXT_CHARS - 1,
        ),
    ):
        with pytest.raises(EmptyPagePdfError, match="text too thin"):
            capture_url_as_pdf(page, "https://example.com/a", dest)
    assert not dest.is_file()
    page.goto.assert_called_once()
    assert page.goto.call_args.kwargs.get("wait_until") == "load"
    page.wait_for_load_state.assert_called()


def test_capture_url_as_pdf_rejects_small_bytes(tmp_path: Path):
    page = MagicMock()
    page.evaluate.return_value = {"body_len": 5000, "title": "T"}
    dest = tmp_path / "out.pdf"

    def fake_pdf(*, path, **_kwargs):
        Path(path).write_bytes(b"%PDF-tiny")

    page.pdf.side_effect = fake_pdf

    with patch(
        "crawler.sources.page_pdf_capture._dismiss_cookie_banner",
        return_value=None,
    ):
        with pytest.raises(EmptyPagePdfError, match="too small"):
            capture_url_as_pdf(page, "https://example.com/a", dest)
    assert not dest.is_file()


def test_capture_url_as_pdf_ok(tmp_path: Path):
    page = MagicMock()

    def _eval(script, *args, **kwargs):
        s = str(script)
        if "body_len" in s and "Math.max" in s:
            return {"body_len": 5000, "title": "T"}
        if "setProperty" in s and "opacity" in s:
            return True
        return None

    page.evaluate.side_effect = _eval
    dest = tmp_path / "out.pdf"

    def fake_pdf(*, path, **_kwargs):
        Path(path).write_bytes(b"%PDF" + b"x" * (DEFAULT_MIN_PDF_BYTES + 10))

    page.pdf.side_effect = fake_pdf

    with (
        patch(
            "crawler.sources.page_pdf_capture._dismiss_cookie_banner",
            return_value="#onetrust-accept-btn-handler",
        ),
        patch(
            "crawler.sources.page_pdf_capture.pdf_extract_char_count",
            return_value=500,
        ),
    ):
        meta = capture_url_as_pdf(page, "https://example.com/a", dest)
    assert meta["bytes"] >= DEFAULT_MIN_PDF_BYTES
    assert meta["pdf_text_len"] == 500
    assert meta["cookie_clicked"] == "#onetrust-accept-btn-handler"
    assert meta["opacity_forced"] is True
    assert dest.is_file()
    assert page.goto.call_args.kwargs.get("wait_until") == "load"
    page.wait_for_load_state.assert_any_call("networkidle", timeout=15_000)
    page.wait_for_function.assert_called()
    page.wait_for_timeout.assert_any_call(300)


def test_ensure_body_painted_forces_when_opacity_zero():
    page = MagicMock()
    page.evaluate.return_value = True
    assert _ensure_body_painted(page) is True
    js = page.evaluate.call_args[0][0]
    assert "opacity" in js
    assert "important" in js


def test_ensure_body_painted_noop_when_already_visible():
    page = MagicMock()
    page.evaluate.return_value = False
    assert _ensure_body_painted(page) is False
