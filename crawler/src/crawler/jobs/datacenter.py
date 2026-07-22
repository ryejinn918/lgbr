"""Download datacenter research PDFs from Fnguide SearchReport."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from patchright.sync_api import Page

from crawler import reports_store
from crawler.asset_id import DOWNLOADS_ROOT
from crawler.crawl_log import CrawlLogger

SEARCH_URL = "https://www.fnguide.com/Research/SearchReport"
KEYWORD = "데이터센터"
SOURCE = reports_store.SOURCE_FNGUIDE
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
MAX_LIST_PAGES = 40


@dataclass
class DatacenterJobSummary:
    downloaded: list[str] = field(default_factory=list)
    listed: int = 0
    skipped_blind: int = 0
    skipped_existing: int = 0
    skipped_no_download: int = 0
    failed: int = 0
    stopped: bool = False

    def as_message(self) -> str:
        files = ", ".join(Path(p).name for p in self.downloaded) or "-"
        parts = [
            f"downloaded={len(self.downloaded)}",
            f"listed={self.listed}",
            f"skipped_blind={self.skipped_blind}",
            f"skipped_existing={self.skipped_existing}",
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
            "listed": self.listed,
            "skipped_blind": self.skipped_blind,
            "skipped_existing": self.skipped_existing,
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
    crawl_id: str | None = None,
    asset_id: str | None = None,
) -> DatacenterJobSummary:
    """Apply fixed filters, then download up to `limit` new PDFs.

    Every list row is upserted into `reports`. Skips 본문 제한 and
    already-downloaded (file_path/disk) rows for download; they do not count
    toward `limit`.
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")
    download_dir.mkdir(parents=True, exist_ok=True)
    summary = DatacenterJobSummary()
    stop = should_stop or (lambda: False)
    log = logger

    already = reports_store.downloaded_keys(SOURCE) | reports_store.disk_rpt_ids(
        root=DOWNLOADS_ROOT
    )
    if log:
        log.emit(
            level="info",
            stage="download",
            event="existing_loaded",
            count=len(already),
        )
        log.set_progress(
            limit=limit,
            downloaded=0,
            listed=0,
            skipped_existing=0,
            existing_known=len(already),
            stage="filter",
        )

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
        blind_rows = [
            c
            for c in candidates
            if c["blind"] and c["rpt_id"] not in seen
        ]
        existing_rows = [
            c
            for c in candidates
            if not c["blind"]
            and c["rpt_id"] not in seen
            and c["rpt_id"] in already
        ]
        work_rows = [
            c
            for c in candidates
            if not c["blind"]
            and c["rpt_id"] not in seen
            and c["rpt_id"] not in already
        ]
        if log:
            log.emit(
                level="info",
                stage="list",
                event="page",
                list_page=list_page,
                total=len(candidates),
                candidates=len(work_rows),
                blind=len(blind_rows),
                existing=len(existing_rows),
            )
            log.set_progress(
                stage="list",
                list_page=list_page,
                candidates=len(work_rows),
                blind=len(blind_rows),
                downloaded=len(summary.downloaded),
                skipped_blind=summary.skipped_blind,
                skipped_existing=summary.skipped_existing,
                limit=limit,
            )

        progressed = False

        def _attrs_for(cand: dict[str, Any], *, blind: bool) -> dict[str, Any]:
            attrs = {
                "rpt_id": cand["rpt_id"],
                "provider": cand.get("provider"),
                "stock": cand.get("stock"),
                "blind": blind,
            }
            if asset_id:
                attrs["asset_id"] = asset_id
            return {k: v for k, v in attrs.items() if v is not None}

        for cand in candidates:
            rpt_id = cand["rpt_id"]
            if not rpt_id or rpt_id in seen:
                continue
            blind = bool(cand["blind"])
            try:
                reports_store.upsert_listed(
                    source=SOURCE,
                    source_key=rpt_id,
                    crawl_id=crawl_id,
                    title=cand.get("title") or rpt_id,
                    author=cand.get("author"),
                    published_at=cand.get("published_at"),
                    page_count=cand.get("page_count"),
                    status=(
                        reports_store.STATUS_BLIND
                        if blind
                        else reports_store.STATUS_LISTED
                    ),
                    attrs=_attrs_for(cand, blind=blind),
                )
                summary.listed += 1
            except Exception as exc:
                if log:
                    log.emit(
                        level="warn",
                        stage="list",
                        event="list_upsert_failed",
                        rpt_id=rpt_id,
                        error=str(exc),
                    )

        if log:
            log.set_progress(
                stage="list",
                listed=summary.listed,
                downloaded=len(summary.downloaded),
                skipped_blind=summary.skipped_blind,
                skipped_existing=summary.skipped_existing,
                limit=limit,
                list_page=list_page,
            )

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

        for cand in existing_rows:
            rpt_id = cand["rpt_id"]
            seen.add(rpt_id)
            progressed = True
            summary.skipped_existing += 1
            if log:
                log.emit(
                    level="info",
                    stage="list",
                    event="item_skip",
                    rpt_id=rpt_id,
                    title=cand["title"],
                    reason="already_downloaded",
                    list_page=list_page,
                )
                log.set_progress(
                    stage="list",
                    listed=summary.listed,
                    skipped_existing=summary.skipped_existing,
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
                    skipped_existing=summary.skipped_existing,
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
                try:
                    reports_store.mark_status(
                        source=SOURCE,
                        source_key=rpt_id,
                        status=reports_store.STATUS_NO_DOWNLOAD,
                        crawl_id=crawl_id,
                        attrs={"blind": False, "no_custom_download": True},
                    )
                except Exception:
                    pass
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
                        listed=summary.listed,
                        limit=limit,
                    )
                continue
            except Exception as exc:
                summary.failed += 1
                try:
                    reports_store.mark_status(
                        source=SOURCE,
                        source_key=rpt_id,
                        status=reports_store.STATUS_FAILED,
                        crawl_id=crawl_id,
                        attrs={"error": str(exc)[:500]},
                    )
                except Exception:
                    pass
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

            attrs = _attrs_for(cand, blind=False)
            try:
                reports_store.mark_downloaded(
                    source=SOURCE,
                    source_key=rpt_id,
                    crawl_id=crawl_id,
                    title=title or rpt_id,
                    author=cand.get("author"),
                    published_at=cand.get("published_at"),
                    page_count=cand.get("page_count"),
                    file_path=str(path),
                    file_name=path.name,
                    attrs=attrs,
                )
            except Exception as exc:
                if log:
                    log.emit(
                        level="warn",
                        stage="download",
                        event="report_meta_failed",
                        rpt_id=rpt_id,
                        error=str(exc),
                    )
            already.add(rpt_id)
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
                    listed=summary.listed,
                    skipped_blind=summary.skipped_blind,
                    skipped_existing=summary.skipped_existing,
                    limit=limit,
                    current_rpt_id=rpt_id,
                )
            if touch:
                touch()
            if len(summary.downloaded) >= limit:
                break
        if summary.stopped or len(summary.downloaded) >= limit:
            break
        next_ok, next_detail = _goto_next_list_page(page)
        if not progressed or not next_ok:
            if log:
                log.emit(
                    level="info",
                    stage="list",
                    event="no_more_pages",
                    list_page=list_page,
                    **next_detail,
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
            listed=detail["listed"],
            skipped_blind=detail["skipped_blind"],
            skipped_existing=detail["skipped_existing"],
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
          const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
          const headers = [...document.querySelectorAll('table thead th, table tr:first-child th')]
            .map(th => norm(th.innerText));
          const idxOf = (...names) => {
            for (const n of names) {
              const i = headers.findIndex(h => h.includes(n));
              if (i >= 0) return i;
            }
            return -1;
          };
          const iDate = idxOf('작성일', '날짜');
          const iStock = idxOf('종목');
          const iTitle = idxOf('제목');
          const iAuthor = idxOf('작성자');
          const iProvider = idxOf('제공사', '증권사');
          const iPages = idxOf('페이지수', '페이지');

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
            const rowText = norm(root?.innerText || a.innerText || '');
            const tds = root ? [...root.querySelectorAll('td')].map(td => norm(td.innerText)) : [];
            const cell = (i, fallback) => (i >= 0 && tds[i] != null ? tds[i] : (fallback || ''));
            const pageRaw = cell(iPages >= 0 ? iPages : 5, '');
            const pageDigits = (pageRaw || '').replace(/\\D/g, '');
            const pages = pageDigits ? parseInt(pageDigits, 10) : null;
            out.push({
              rpt_id: m[1],
              href,
              title: norm(a.innerText) || cell(iTitle, ''),
              published_at: cell(iDate >= 0 ? iDate : 0, ''),
              stock: cell(iStock >= 0 ? iStock : 1, ''),
              author: cell(iAuthor >= 0 ? iAuthor : 3, ''),
              provider: cell(iProvider >= 0 ? iProvider : 4, ''),
              page_count: pages,
              row_text: rowText.slice(0, 300),
              has_tag: !!(tag && /본문/.test(tag.innerText || '')),
              headers,
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
        published_raw = str(row.get("published_at") or "").strip()
        published_at: str | None = None
        if published_raw:
            # normalize 2026.07.13 / 2026-07-13 / 2026/07/13
            m = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", published_raw)
            if m:
                published_at = (
                    f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                )
        page_count = row.get("page_count")
        try:
            page_count_i = int(page_count) if page_count is not None else None
        except (TypeError, ValueError):
            page_count_i = None
        candidates.append(
            {
                "rpt_id": rpt_id,
                "href": row.get("href") or viewer_url(rpt_id),
                "title": (row.get("title") or "").strip(),
                "author": (row.get("author") or "").strip() or None,
                "provider": (row.get("provider") or "").strip() or None,
                "stock": (row.get("stock") or "").strip() or None,
                "published_at": published_at,
                "page_count": page_count_i,
                "blind": is_blind_candidate(
                    row_text=str(row.get("row_text") or ""),
                    has_tag=bool(row.get("has_tag")),
                ),
            }
        )
    return candidates


def _goto_next_list_page(page: Page) -> tuple[bool, dict[str, Any]]:
    """Advance SearchReport list pagination. Returns (ok, detail)."""
    detail: dict[str, Any] = {}
    # Prefer explicit next controls, then page-number + 1.
    selectors = [
        "a.next:not(.disabled):not([aria-disabled='true'])",
        "button.next:not(:disabled)",
        "a[aria-label='다음']:not([aria-disabled='true'])",
        "button[aria-label='다음']:not(:disabled)",
        ".paging a.next, .pagination a.next, .paginate a.next",
        "a.page-next, button.page-next",
    ]
    for sel in selectors:
        loc = page.locator(sel)
        if loc.count() == 0:
            continue
        target = loc.first
        try:
            cls = target.get_attribute("class") or ""
            if "disabled" in cls or "off" in cls:
                continue
            before = page.evaluate(
                """() => [...document.querySelectorAll('a[href*="rptId="]')]
                  .slice(0,3).map(a => a.href).join('|')"""
            )
            target.click(timeout=5000)
            page.wait_for_timeout(LIST_WAIT_MS)
            after = page.evaluate(
                """() => [...document.querySelectorAll('a[href*="rptId="]')]
                  .slice(0,3).map(a => a.href).join('|')"""
            )
            if after and after != before:
                detail["via"] = sel
                return True, detail
        except Exception as exc:
            detail["error"] = str(exc)
            continue

    # Click numeric page = current + 1
    clicked = page.evaluate(
        """() => {
          const roots = [
            ...document.querySelectorAll('.paging, .pagination, .paginate, .page-nav, nav')
          ];
          const scope = roots.length ? roots[roots.length - 1] : document.body;
          const links = [...scope.querySelectorAll('a, button')];
          let current = null;
          for (const el of links) {
            const t = (el.innerText || '').trim();
            const cls = String(el.className || '');
            if (/^\\d+$/.test(t) && /(active|current|on|selected)/i.test(cls)) {
              current = parseInt(t, 10);
              break;
            }
            if (el.getAttribute('aria-current') === 'page' && /^\\d+$/.test(t)) {
              current = parseInt(t, 10);
              break;
            }
          }
          if (current == null) {
            // sometimes current is a span
            for (const el of scope.querySelectorAll('span, strong, em')) {
              const t = (el.innerText || '').trim();
              if (/^\\d+$/.test(t) && el.closest('a,button') == null) {
                current = parseInt(t, 10);
                break;
              }
            }
          }
          if (current == null) return {ok: false, reason: 'no_current_page'};
          const nextNum = String(current + 1);
          const next = links.find(el => (el.innerText || '').trim() === nextNum);
          if (!next) return {ok: false, reason: 'no_next_number', current};
          next.click();
          return {ok: true, current, next: current + 1};
        }"""
    )
    if isinstance(clicked, dict) and clicked.get("ok"):
        page.wait_for_timeout(LIST_WAIT_MS)
        detail.update({k: v for k, v in clicked.items() if k != "ok"})
        detail["via"] = "page_number"
        return True, detail
    if isinstance(clicked, dict):
        detail.update(clicked)
    detail.setdefault("via", "none")
    return False, detail


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
