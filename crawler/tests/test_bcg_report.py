"""BCG HTTP search job: detail PDF download and no-pdf page capture fallback."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

from crawler.jobs.bcg_report import (
    DEFAULT_ITEM_DELAY_SECONDS,
    BcgJobSummary,
    _process_item,
    run_bcg_search_job,
)
from crawler.sources.bcg_http import BcgListItem


def test_default_item_delay_is_two_seconds() -> None:
    assert DEFAULT_ITEM_DELAY_SECONDS == 2.0


def test_process_item_downloads_http_pdf(tmp_path: Path) -> None:
    item = BcgListItem(
        source_key="2026/improving-governance-in-joint-ventures",
        url=(
            "https://www.bcg.com/publications/2026/"
            "improving-governance-in-joint-ventures"
        ),
        title="The Board Can Make or Break a Joint Venture",
        published_at=date(2026, 7, 30),
        publish_date_raw="July 30, 2026",
    )
    pdf_url = (
        "https://web-assets.bcg.com/pdf-src/prod-live/"
        "improving-governance-in-joint-ventures.pdf"
    )
    summary = BcgJobSummary()
    progress: dict = {}
    already: set[str] = set()

    with (
        patch("crawler.jobs.bcg_report.reports_store") as store,
        patch(
            "crawler.jobs.bcg_report.fetch_detail_meta",
            return_value=(pdf_url, date(2026, 7, 30)),
        ),
        patch("crawler.jobs.bcg_report.download_pdf", return_value=2458478),
        patch("crawler.jobs.bcg_report.pdf_page_count", return_value=8),
        patch("crawler.jobs.bcg_report.collection_jobs_store"),
        patch(
            "crawler.jobs.bcg_report.process_no_pdf_with_page_capture"
        ) as page_cap,
    ):
        outcome = _process_item(
            item,
            catalog_id="us",
            profile_id="report",
            list_url="https://www.bcg.com/publications",
            cutoff=date(2026, 5, 1),
            summary=summary,
            already=already,
            download_dir=tmp_path,
            progress=progress,
            job_id=uuid4(),
            session=MagicMock(),
            capture=MagicMock(),
        )

    assert outcome == "ok"
    assert len(summary.downloaded) == 1
    store.mark_downloaded.assert_called_once()
    page_cap.assert_not_called()
    assert item.source_key in already


def test_process_item_falls_back_to_page_pdf_when_no_href(tmp_path: Path) -> None:
    item = BcgListItem(
        source_key="2026/industrial-ai-commercialization",
        url=(
            "https://www.bcg.com/publications/2026/"
            "industrial-ai-commercialization"
        ),
        title="Beyond the Machine",
        published_at=date(2026, 7, 30),
        publish_date_raw="July 30, 2026",
    )
    summary = BcgJobSummary()
    progress: dict = {}
    already: set[str] = set()

    with (
        patch("crawler.jobs.bcg_report.reports_store"),
        patch(
            "crawler.jobs.bcg_report.fetch_detail_meta",
            return_value=(None, date(2026, 7, 30)),
        ),
        patch("crawler.jobs.bcg_report.collection_jobs_store"),
        patch(
            "crawler.jobs.bcg_report.process_no_pdf_with_page_capture"
        ) as page_cap,
        patch("crawler.jobs.bcg_report.download_pdf") as dl,
    ):
        outcome = _process_item(
            item,
            catalog_id="us",
            profile_id="report",
            list_url="https://www.bcg.com/publications",
            cutoff=date(2026, 5, 1),
            summary=summary,
            already=already,
            download_dir=tmp_path,
            progress=progress,
            job_id=uuid4(),
            session=MagicMock(),
            capture=MagicMock(),
        )

    assert outcome == "ok"
    page_cap.assert_called_once()
    dl.assert_not_called()


def test_run_job_respects_limit_one(tmp_path: Path) -> None:
    job_id = uuid4()
    items = [
        BcgListItem(
            source_key=f"2026/item-{i}",
            url=f"https://www.bcg.com/publications/2026/item-{i}",
            title=f"Sample BCG Report Title Number {i}",
            published_at=date(2026, 7, 15),
            publish_date_raw="July 15, 2026",
        )
        for i in range(3)
    ]

    with (
        patch(
            "crawler.jobs.bcg_report.collection_jobs_store"
        ) as jobs,
        patch("crawler.jobs.bcg_report.reports_store") as store,
        patch(
            "crawler.jobs.bcg_report.fetch_list_items",
            return_value=items,
        ),
        patch(
            "crawler.jobs.bcg_report.fetch_detail_meta",
            return_value=(
                "https://web-assets.bcg.com/pdf-src/x.pdf",
                date(2026, 7, 15),
            ),
        ),
        patch("crawler.jobs.bcg_report.download_pdf", return_value=100),
        patch("crawler.jobs.bcg_report.pdf_page_count", return_value=2),
        patch("crawler.jobs.bcg_report.make_session", return_value=MagicMock()),
        patch("crawler.jobs.bcg_report.pace_after_item"),
        patch(
            "crawler.jobs.bcg_report.LazyCaptureBrowser",
            return_value=MagicMock(),
        ),
        patch(
            "crawler.jobs.bcg_report.downloads_dir",
            return_value=tmp_path,
        ),
    ):
        jobs.claim_job.return_value = {
            "source": "bcg",
            "capability": "search",
        }
        store.downloaded_keys.return_value = set()
        jobs.stop_requested.return_value = False
        jobs.end_job.side_effect = lambda jid, **kw: {
            "state": "error" if kw.get("error") else "ended",
            "message": kw.get("message"),
        }

        result = run_bcg_search_job(
            job_id,
            profile="report",
            period_months=3,
            max_pages=1,
            limit=1,
            item_delay_seconds=0,
            download_root=tmp_path,
        )

    assert result["state"] == "ended"
    assert "downloaded=1" in (result.get("message") or "")
    assert store.mark_downloaded.call_count == 1
