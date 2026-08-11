"""HBR search job: existing rows skip upsert so list dates cannot regress."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

from crawler.jobs.hbr_report import HbrJobSummary, _process_item
from crawler.sources.hbr_browser import HbrListItem


def test_process_item_skips_upsert_for_existing() -> None:
    item = HbrListItem(
        source_key="ai-and-it-teams-often-clash-but-they-dont-have-to",
        url="https://hbr.org/2026/07/ai-and-it-teams-often-clash-but-they-dont-have-to",
        title="AI and IT Teams Often Clash",
        published_at=None,
        publish_date_raw="",
        url_ym=date(2026, 7, 1),
    )
    summary = HbrJobSummary()
    progress: dict = {}
    already = {item.source_key}

    with (
        patch("crawler.jobs.hbr_report.reports_store") as store,
        patch("crawler.jobs.hbr_report.collection_jobs_store"),
        patch("crawler.jobs.hbr_report.capture_article_pdf") as capture,
    ):
        _process_item(
            MagicMock(),
            item,
            catalog_id="us",
            summary=summary,
            already=already,
            download_dir=Path("/tmp"),
            progress=progress,
            job_id=uuid4(),
        )

    assert summary.skipped_existing == 1
    store.upsert_listed.assert_not_called()
    store.mark_downloaded.assert_not_called()
    capture.assert_not_called()


def test_process_item_upserts_then_prefers_detail_date(tmp_path: Path) -> None:
    item = HbrListItem(
        source_key="bring-back-managing-for-value",
        url="https://hbr.org/2026/07/bring-back-managing-for-value",
        title="Bring Back Managing for Value",
        published_at=None,
        publish_date_raw="",
        url_ym=date(2026, 7, 1),
    )
    summary = HbrJobSummary()
    progress: dict = {}
    already: set[str] = set()
    dest_dir = tmp_path / "dl"
    dest_dir.mkdir()

    with (
        patch("crawler.jobs.hbr_report.reports_store") as store,
        patch("crawler.jobs.hbr_report.collection_jobs_store"),
        patch(
            "crawler.jobs.hbr_report.capture_article_pdf",
            return_value={
                "title": item.title,
                "published_at": date(2026, 7, 31),
                "date_raw": "2026-07-31",
                "bytes": 2048,
                "body_len": 5000,
                "capture": "page_pdf",
            },
        ),
        patch("crawler.jobs.hbr_report.pdf_page_count", return_value=3),
    ):
        _process_item(
            MagicMock(),
            item,
            catalog_id="us",
            summary=summary,
            already=already,
            download_dir=dest_dir,
            progress=progress,
            job_id=uuid4(),
        )

    store.upsert_listed.assert_called_once()
    assert store.upsert_listed.call_args.kwargs["published_at"] is None
    store.mark_downloaded.assert_called_once()
    assert store.mark_downloaded.call_args.kwargs["published_at"] == date(2026, 7, 31)
    assert item.source_key in already
    assert len(summary.downloaded) == 1
