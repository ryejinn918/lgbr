"""Download datacenter research PDFs from Fnguide SearchReport."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from patchright.sync_api import Page

from crawler.crawl_log import CrawlLogger

SEARCH_URL = "https://www.fnguide.com/Research/SearchReport"
KEYWORD = "데이터센터"
SECTORS = (
    "에너지",
    "소재",
    "산업재",
    "금융",
    "IT",
    "커뮤니케이션서비스",
    "유틸리티",
)
VIEWER_WAIT_MS = 3500
LIST_WAIT_MS = 2500
MAX_LIST_PAGES = 20


@dataclass
class DatacenterJobSummary:
    downloaded: list[str] = field(default_factory=list)
    skipped_blind: int = 0
    skipped_no_download: int = 0
    failed: int = 0
    stopped: bool = False

    def as_message(self) -> str:
        files = ", ".join(Path(p).name for p in self.downloaded) or "-"
        parts = [
            f"downloaded={len(self.downloaded)}",
            f"skipped_blind={self.skipped_blind}",
            f"skipped_no_download={self.skipped_no_download}",
            f"failed={self.failed}",
            f"files={files}",
        ]
        if self.stopped:
            parts.append("stopped=1")
        return "; ".join(parts)

    def as_detail(self) -> dict[str, Any]:
        return {
            "downloaded": len(self.downloaded),
            "skipped_blind": self.skipped_blind,
            "skipped_no_download": self.skipped_no_download,
            "failed": self.failed,
            "stopped": self.stopped,
            "files": [Path(p).name for p in self.downloaded],
        }


def is_blind_candidate(*, row_text: str, has_tag: bool) -> bool:
    if has_tag:
        return True
    return bool(re.search(r"본문\s*제한|본문제한", row_text))


def rpt_id_from_href(href: str) -> str | None:
    if not href:
        return None
    if "rptId=" in href:
        qs = parse_qs(urlparse(href).query)
        values = qs.get("rptId") or []
        if values:
            return values[0]
    match = re.search(r"rptId[=:](\d+)", href)
    return match.group(1) if match else None


def viewer_url(rpt_id: str) -> str:
    return f"https://www.fnguide.com/Research/PdfViewer?rptId={rpt_id}"


def run_datacenter_job(
    page: Page,
    *,
    limit: int,
    download_dir: Path,
    should_stop: Callable[[], bool] | None = None,
    touch: Callable[[], Any] | None = None,
    logger: CrawlLogger | None = None,
) -> DatacenterJobSummary:
    """Apply fixed filters, then download up to `limit` PDFs.

    List rows already tagged 본문 제한 are skipped (logged) and do not count
    toward `limit`. Only successful downloads increment the counter.
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")
    download_dir.mkdir(parents=True, exist_ok=True)
    summary = DatacenterJobSummary()
    stop = should_stop or (lambda: False)
    log = logger

    if log:
        log.set_progress(limit=limit, downloaded=0, stage="filter")

    if log:
        with log.stage("filter", keyword=KEYWORD, page_cnt_min=10):
            _apply_filters(page)
    else:
        _apply_filters(page)
    if touch:
        touch()
    _sort_by_page_count_desc(page)
    if log:
        log.emit(level="info", stage="filter", event="sorted", by="page_count_desc")

    seen: set[str] = set()
    list_page = 0
    while len(summary.downloaded) < limit and list_page < MAX_LIST_PAGES:
        if stop():
            summary.stopped = True
            if log:
                log.emit(level="warn", stage="list", event="stopped", list_page=list_page)
            break
        candidates = _list_candidates(page)
        # List-tagged 본문 제한 is excluded from the downloadable count; still logged.
        blind_rows = [c for c in candidates if c["blind"] and c["rpt_id"] not in seen]
        work_rows = [c for c in candidates if not c["blind"] and c["rpt_id"] not in seen]
        if log:
            log.emit(
                level="info",
                stage="list",
                event="page",
                list_page=list_page,
                total=len(candidates),
                candidates=len(work_rows),
                blind=len(blind_rows),
            )
            log.set_progress(
                stage="list",
                list_page=list_page,
                candidates=len(work_rows),
                blind=len(blind_rows),
                downloaded=len(summary.downloaded),
                skipped_blind=summary.skipped_blind,
                limit=limit,
            )

        progressed = False
        for cand in blind_rows:
            rpt_id = cand["rpt_id"]
            seen.add(rpt_id)
            progressed = True
            summary.skipped_blind += 1
            if log:
                log.emit(
                    level="info",
                    stage="list",
                    event="item_skip",
                    rpt_id=rpt_id,
                    title=cand["title"],
                    reason="blind",
                    list_page=list_page,
                )
                log.set_progress(
                    stage="list",
                    skipped_blind=summary.skipped_blind,
                    downloaded=len(summary.downloaded),
                    limit=limit,
                    list_page=list_page,
                )

        for cand in work_rows:
            if stop():
                summary.stopped = True
                if log:
                    log.emit(
                        level="warn",
                        stage="download",
                        event="stopped",
                        list_page=list_page,
                    )
                break
            rpt_id = cand["rpt_id"]
            if rpt_id in seen:
                continue
            seen.add(rpt_id)
            progressed = True
            title = cand["title"]
            if log:
                log.set_progress(
                    stage="download",
                    current_rpt_id=rpt_id,
                    downloaded=len(summary.downloaded),
                    skipped_blind=summary.skipped_blind,
                    limit=limit,
                    list_page=list_page,
                )
            try:
                path = _download_one(
                    page,
                    rpt_id=rpt_id,
                    title=title,
                    download_dir=download_dir,
                    index=len(summary.downloaded) + 1,
                )
            except _NoDownloadError as exc:
                summary.skipped_no_download += 1
                if log:
                    log.emit(
                        level="info",
                        stage="download",
                        event="item_skip",
                        rpt_id=rpt_id,
                        title=title,
                        reason="no_custom_download",
                        error=str(exc),
                    )
                    log.set_progress(
                        stage="download",
                        skipped_no_download=summary.skipped_no_download,
                        downloaded=len(summary.downloaded),
                        limit=limit,
                    )
                continue
            except Exception as exc:
                summary.failed += 1
                if log:
                    log.emit(
                        level="error",
                        stage="download",
                        event="item_fail",
                        rpt_id=rpt_id,
                        title=title,
                        error=str(exc),
                    )
                continue
            summary.downloaded.append(str(path))
            if log:
                log.emit(
                    level="info",
                    stage="download",
                    event="item_ok",
                    rpt_id=rpt_id,
                    title=title,
                    path=str(path),
                )
                log.set_progress(
                    stage="download",
                    downloaded=len(summary.downloaded),
                    skipped_blind=summary.skipped_blind,
                    limit=limit,
                    current_rpt_id=rpt_id,
                )
            if touch:
                touch()
            if len(summary.downloaded) >= limit:
                break
        if summary.stopped or len(summary.downloaded) >= limit:
            break
        if not progressed or not _goto_next_list_page(page):
            if log:
                log.emit(
                    level="info",
                    stage="list",
                    event="no_more_pages",
                    list_page=list_page,
                )
            break
        list_page += 1
        if touch:
            touch()

    if log:
        detail = summary.as_detail()
        log.emit(level="info", stage="download", event="crawl_end", **detail)
        log.set_progress(
            stage="done",
            limit=limit,
            downloaded=detail["downloaded"],
            skipped_blind=detail["skipped_blind"],
            skipped_no_download=detail["skipped_no_download"],
            failed=detail["failed"],
            stopped=detail["stopped"],
        )
    return summary


class _NoDownloadError(RuntimeError):
    """Viewer has no #customDownload (typically body-restricted)."""


def _apply_filters(page: Page) -> None:
    page.goto(SEARCH_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    page.locator("button.dropdown-text").first.click()
    page.wait_for_timeout(300)
    page.locator("li span.item", has_text="제목").first.click()
    page.wait_for_timeout(300)

    page.locator("#srchKeyword").fill(KEYWORD)
    page.wait_for_timeout(200)

    page.locator("button.select-box.flat-select", has_text="페이지").first.click()
    page.wait_for_timeout(300)
    page.locator("li span.item", has_text="10p 이상").first.click()
    page.wait_for_timeout(300)

    # period defaults to 3 months; force if control exists
    period = page.locator("#period")
    if period.count():
        try:
            if period.input_value() != "3":
                page.locator("button.select-box.flat-select", has_text="개월").first.click()
                page.wait_for_timeout(200)
                page.locator("li span.item", has_text="3개월").first.click()
                page.wait_for_timeout(200)
        except Exception:
            pass

    page.locator("#sectorFilterBtn").click()
    page.wait_for_timeout(500)
    for name in SECTORS:
        loc = page.locator("label", has_text=name)
        target = None
        for i in range(loc.count()):
            text = (loc.nth(i).inner_text() or "").strip()
            if text == name:
                target = loc.nth(i)
                break
        if target is None and loc.count():
            target = loc.first
        if target is None:
            continue
        box = target.locator("input[type=checkbox]")
        if box.count() == 0:
            target.click()
        elif not box.first.is_checked():
            box.first.check()
    page.wait_for_timeout(300)

    apply = page.get_by_role("button", name="적용")
    if apply.count() == 0:
        apply = page.get_by_text("적용", exact=True)
    if apply.count():
        apply.first.click()
        page.wait_for_timeout(400)

    page.locator("#srchBtn").click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(LIST_WAIT_MS)


def _sort_by_page_count_desc(page: Page) -> None:
    sort_btn = page.locator("button.btn--sort", has_text="페이지수")
    if sort_btn.count() == 0:
        sort_btn = page.get_by_role("button", name=re.compile("페이지수"))
    if sort_btn.count() == 0:
        return

    def page_nums() -> list[int]:
        rows = page.evaluate(
            """() => [...document.querySelectorAll('table tr')].slice(1, 8).map(tr => {
              const tds = [...tr.querySelectorAll('td')].map(
                td => td.innerText.trim().replace(/\\s+/g, ' ')
              );
              return tds[5] || '';
            })"""
        )
        out: list[int] = []
        for raw in rows:
            digits = re.sub(r"\D", "", str(raw) or "")
            if digits:
                out.append(int(digits))
        return out

    before = page_nums()
    sort_btn.first.click()
    page.wait_for_timeout(1500)
    mid = page_nums()
    if mid and before and mid[0] < max(before + mid):
        sort_btn.first.click()
        page.wait_for_timeout(1500)


def _list_candidates(page: Page) -> list[dict[str, Any]]:
    rows = page.evaluate(
        """() => {
          const out = [];
          const seen = new Set();
          for (const a of document.querySelectorAll('a[href*="rptId="]')) {
            const href = a.href || '';
            const m = href.match(/rptId=(\\d+)/);
            if (!m || seen.has(m[1])) continue;
            seen.add(m[1]);
            let root = a.closest('tr, li, article, .list-item, .item') || a.parentElement;
            if (root && !root.querySelector('.service-state-tag') && root.parentElement) {
              const parent = root.parentElement;
              if (parent.querySelector('.service-state-tag')) root = parent;
            }
            const tag = root?.querySelector?.('.service-state-tag');
            const rowText = (root?.innerText || a.innerText || '').replace(/\\s+/g, ' ').trim();
            const tds = root ? [...root.querySelectorAll('td')].map(
              td => td.innerText.trim().replace(/\\s+/g, ' ')
            ) : [];
            let pages = null;
            if (tds.length >= 6) {
              const digits = (tds[5] || '').replace(/\\D/g, '');
              if (digits) pages = parseInt(digits, 10);
            }
            out.push({
              rpt_id: m[1],
              href,
              title: (a.innerText || '').trim(),
              row_text: rowText.slice(0, 300),
              has_tag: !!(tag && /본문/.test(tag.innerText || '')),
              pages,
            });
          }
          return out;
        }"""
    )
    candidates: list[dict[str, Any]] = []
    for row in rows:
        rpt_id = str(row.get("rpt_id") or "")
        if not rpt_id:
            continue
        candidates.append(
            {
                "rpt_id": rpt_id,
                "href": row.get("href") or viewer_url(rpt_id),
                "title": (row.get("title") or "").strip(),
                "blind": is_blind_candidate(
                    row_text=str(row.get("row_text") or ""),
                    has_tag=bool(row.get("has_tag")),
                ),
                "pages": row.get("pages"),
            }
        )
    return candidates


def _goto_next_list_page(page: Page) -> bool:
    next_btn = page.locator("a.next, button.next, a[aria-label='다음'], button[aria-label='다음']")
    if next_btn.count() == 0:
        next_btn = page.get_by_role("link", name=re.compile(r"^다음|›|>$"))
    if next_btn.count() == 0:
        return False
    target = next_btn.first
    try:
        disabled = target.get_attribute("aria-disabled") == "true" or "disabled" in (
            target.get_attribute("class") or ""
        )
        if disabled:
            return False
        target.click()
        page.wait_for_timeout(LIST_WAIT_MS)
        return True
    except Exception:
        return False


def _download_one(
    page: Page,
    *,
    rpt_id: str,
    title: str,
    download_dir: Path,
    index: int,
) -> Path:
    ctx = page.context
    viewer = ctx.new_page()
    try:
        viewer.goto(viewer_url(rpt_id), wait_until="domcontentloaded")
        viewer.wait_for_timeout(VIEWER_WAIT_MS)
        btn = viewer.locator("#customDownload")
        if btn.count() == 0:
            raise _NoDownloadError(f"no customDownload for rptId={rpt_id}")
        # hidden native Syncfusion control must not be used
        box = btn.first.bounding_box()
        if not box or box.get("width", 0) <= 0:
            raise _NoDownloadError(f"customDownload not visible for rptId={rpt_id}")
        with viewer.expect_download(timeout=60_000) as download_info:
            btn.first.click(timeout=10_000)
        download = download_info.value
        suggested = download.suggested_filename or f"{rpt_id}.pdf"
        safe_title = re.sub(r"[^\w\-가-힣]+", "_", title).strip("_")[:60]
        prefix = f"{index:02d}-{rpt_id}"
        name = f"{prefix}-{safe_title}-{suggested}" if safe_title else f"{prefix}-{suggested}"
        dest = download_dir / name
        download.save_as(str(dest))
        if dest.stat().st_size <= 0:
            raise RuntimeError(f"empty download for rptId={rpt_id}")
        return dest
    finally:
        try:
            viewer.close()
        except Exception:
            pass
