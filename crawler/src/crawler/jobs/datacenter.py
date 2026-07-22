"""Datacenter SearchReport crawl — thin wrapper over search_report profiles."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from patchright.sync_api import Page

from crawler.crawl_log import CrawlLogger
from crawler.jobs.search_report import (
    SearchJobSummary,
    get_profile,
    is_blind_candidate,
    rpt_id_from_href,
    run_search_report_job,
    viewer_url,
)

# Re-exports for older imports / tests
DatacenterJobSummary = SearchJobSummary
KEYWORD = "데이터센터"
SECTORS = get_profile("datacenter").sectors


def run_datacenter_job(
    page: Page,
    *,
    limit: int,
    download_dir: Path,
    should_stop: Callable[[], bool] | None = None,
    touch: Callable[[], Any] | None = None,
    logger: CrawlLogger | None = None,
    crawl_id: str | None = None,
    asset_id: str | None = None,
) -> SearchJobSummary:
    return run_search_report_job(
        page,
        profile=get_profile("datacenter"),
        limit=limit,
        download_dir=download_dir,
        should_stop=should_stop,
        touch=touch,
        logger=logger,
        crawl_id=crawl_id,
        asset_id=asset_id,
    )


__all__ = [
    "DatacenterJobSummary",
    "KEYWORD",
    "SECTORS",
    "is_blind_candidate",
    "rpt_id_from_href",
    "run_datacenter_job",
    "viewer_url",
]
