"""KPMG search job: cutoff uses detail date, not stale Cludo list date."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

from crawler.jobs.kpmg_report import KpmgJobSummary, _process_item
from crawler.sources.kpmg_http import KpmgListItem, get_catalog


def test_process_item_uses_detail_date_when_list_date_is_old(tmp_path: Path) -> None:
    cat = get_catalog("us")
    item = KpmgListItem(
        source_key="us/en/articles/2023/insights-2023-coso-icif-report",
        title="Insights from the 2023 COSO ICIF report",
        url=(
            "https://kpmg.com/us/en/articles/2023/"
            "insights-2023-coso-icif-report.html"
        ),
        published_at=date(2023, 3, 28),
        category=None,
    )
    pdf_url = (
        "https://kpmg.com/kpmg-us/content/dam/kpmg/pdf/2023/"
        "coso-icif-for-esg-reporting.pdf"
    )
    summary = KpmgJobSummary()
    progress: dict = {}
    already: set[str] = set()
    dest_dir = tmp_path / "dl"
    dest_dir.mkdir()

    with (
        patch("crawler.jobs.kpmg_report.reports_store") as store,
        patch(
            "crawler.jobs.kpmg_report.fetch_detail_meta",
            return_value=(pdf_url, date(2026, 5, 15)),
        ),
        patch("crawler.jobs.kpmg_report.download_pdf", return_value=1234),
        patch("crawler.jobs.kpmg_report.pdf_page_count", return_value=8),
        patch("crawler.jobs.kpmg_report.collection_jobs_store"),
    ):
        outcome = _process_item(
            item,
            catalog_id=cat.id,
            catalog=cat,
            cutoff=date(2026, 5, 1),
            summary=summary,
            already=already,
            download_dir=dest_dir,
            progress=progress,
            job_id=uuid4(),
            session=MagicMock(),
            capture=MagicMock(),
        )

    assert outcome == "ok"
    assert len(summary.downloaded) == 1
    assert summary.skipped_old == 0
    store.mark_downloaded.assert_called_once()
    assert item.source_key in already


def test_process_item_skips_old_after_detail_confirms(tmp_path: Path) -> None:
    cat = get_catalog("us")
    item = KpmgListItem(
        source_key="us/en/articles/2023/old-report",
        title="Old report",
        url="https://kpmg.com/us/en/articles/2023/old-report.html",
        published_at=date(2023, 1, 1),
        category=None,
    )
    summary = KpmgJobSummary()
    progress: dict = {}
    already: set[str] = set()

    with (
        patch("crawler.jobs.kpmg_report.reports_store"),
        patch(
            "crawler.jobs.kpmg_report.fetch_detail_meta",
            return_value=(
                "https://kpmg.com/kpmg-us/content/dam/kpmg/pdf/2023/x.pdf",
                date(2024, 1, 1),
            ),
        ),
        patch("crawler.jobs.kpmg_report.download_pdf") as dl,
        patch("crawler.jobs.kpmg_report.collection_jobs_store"),
    ):
        outcome = _process_item(
            item,
            catalog_id=cat.id,
            catalog=cat,
            cutoff=date(2026, 5, 1),
            summary=summary,
            already=already,
            download_dir=tmp_path,
            progress=progress,
            job_id=uuid4(),
            session=MagicMock(),
            capture=MagicMock(),
        )

    assert outcome == "old"
    assert summary.skipped_old == 1
    assert summary.downloaded == []
    dl.assert_not_called()
