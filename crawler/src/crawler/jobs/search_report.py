"""Shared Fnguide SearchReport list + download engine (profile-driven)."""

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
from crawler.report_themes import REPORT_THEMES
from crawler.session import capture_filter_failure

SEARCH_URL = "https://www.fnguide.com/Research/SearchReport"
SOURCE = reports_store.SOURCE_FNGUIDE
VIEWER_WAIT_MS = 3500
LIST_WAIT_MS = 2500
MAX_LIST_PAGES = 40
# Keep only reports longer than this (page_count <= N are ignored).
MIN_PAGE_COUNT = 10
FILTER_UI_TIMEOUT_MS = 30_000
FILTER_APPLY_RETRIES = 3

PERIOD_LABELS = {3: "3개월", 6: "6개월", 12: "12개월"}


@dataclass(frozen=True)
class SearchProfile:
    mode: str
    keywords: tuple[str, ...]
    sectors: tuple[str, ...]
    theme: str
    period_months: int = 3
    page_min_label: str = "10p 이상"

    @property
    def keyword(self) -> str:
        """Primary keyword used for a single FnGuide search pass."""
        if not self.keywords:
            raise ValueError(f"empty keywords for mode: {self.mode}")
        return self.keywords[0]


PROFILES: dict[str, SearchProfile] = {
    "ai": SearchProfile(
        mode="ai",
        keywords=("AI", "AI 반도체", "생성형 AI", "LLM"),
        sectors=(
            "IT",
            "커뮤니케이션서비스",
            "금융",
        ),
        theme="ai",
    ),
    "datacenter": SearchProfile(
        mode="datacenter",
        keywords=("데이터센터", "AIDC", "AI 데이터센터", "전력", "냉각"),
        sectors=(
            "에너지",
            "소재",
            "산업재",
            "유틸리티",
            "IT",
        ),
        theme="datacenter",
    ),
    "physical_ai": SearchProfile(
        mode="physical_ai",
        keywords=(
            "피지컬 AI",
            "Physical AI",
            "휴머노이드",
            "Humanoid",
            "로보틱스",
            "로봇",
            "온디바이스 칩",
        ),
        sectors=(),
        theme="physical_ai",
        page_min_label="10p 이상",
    ),
    "appliance": SearchProfile(
        mode="appliance",
        keywords=(
            "가전",
            "백색가전",
            "TV",
            "냉장고",
            "세탁기",
            "청소기",
            "에어컨",
            "디바이스",
            "공조",
            "HVAC",
        ),
        sectors=(),
        theme="appliance",
    ),
    "display": SearchProfile(
        mode="display",
        keywords=("디스플레이", "패널", "OLED"),
        sectors=(),
        theme="display",
    ),
    "automotive": SearchProfile(
        mode="automotive",
        keywords=(
            "자동차",
            "전장",
            "전기차",
            "모빌리티",
            "ESS",
            "EV",
            "배터리",
            "LFP",
            "NCM",
            "SDV",
            "ADV",
        ),
        sectors=(),
        theme="automotive",
    ),
    "petrochemical": SearchProfile(
        mode="petrochemical",
        keywords=(
            "석유화학",
            "석화",
            "화학",
            "케미칼",
            "Chemicals",
            "납사",
        ),
        sectors=(),
        theme="petrochemical",
    ),
}

SEARCH_MODES = frozenset(PROFILES)
# Stable run order for mode=all_profiles (matches frontend SEARCH_PROFILE_MODES).
SEARCH_PROFILE_ORDER = tuple(PROFILES)
ALL_PROFILES_MODE = "all_profiles"


@dataclass
class SearchJobSummary:
    downloaded: list[str] = field(default_factory=list)
    listed: int = 0
    skipped_blind: int = 0
    skipped_existing: int = 0
    skipped_no_download: int = 0
    failed: int = 0
    stopped: bool = False

    def as_message(self) -> str:
        parts = [
            f"downloaded={len(self.downloaded)}",
            f"listed={self.listed}",
            f"blind={self.skipped_blind}",
            f"existing={self.skipped_existing}",
            f"no_dl={self.skipped_no_download}",
            f"failed={self.failed}",
        ]
        if self.stopped:
            parts.append("stopped=1")
        return " ".join(parts)

    def as_detail(self) -> dict[str, Any]:
        return {
            "downloaded": len(self.downloaded),
            "listed": self.listed,
            "skipped_blind": self.skipped_blind,
            "skipped_existing": self.skipped_existing,
            "skipped_no_download": self.skipped_no_download,
            "failed": self.failed,
            "stopped": self.stopped,
        }


def get_profile(mode: str) -> SearchProfile:
    from crawler import profiles_store

    row = profiles_store.get_profile_row(mode)
    if row is not None:
        raw_kw = row.get("keywords") or ()
        keywords = tuple(str(k).strip() for k in raw_kw if str(k).strip())
        if not keywords:
            raise ValueError(f"empty keywords in profile: {mode}")
        return SearchProfile(
            mode=str(row["mode"]),
            keywords=keywords,
            sectors=tuple(row.get("sectors") or ()),
            theme=str(row["mode"]),
            period_months=int(row.get("period_months") or 3),
            page_min_label=str(row.get("page_min_label") or "10p 이상"),
        )
    profile = PROFILES.get(mode)
    if profile is None:
        raise ValueError(f"No search profile for mode: {mode}")
    return profile


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


def run_search_report_job(
    page: Page,
    *,
    profile: SearchProfile,
    limit: int | None = None,
    download_dir: Path,
    should_stop: Callable[[], bool] | None = None,
    touch: Callable[[], Any] | None = None,
    logger: CrawlLogger | None = None,
    crawl_id: str | None = None,
    asset_id: str | None = None,
) -> SearchJobSummary:
    """For each profile keyword: search → download within the period window.

    When ``limit`` is None (default), download every new non-blind hit per keyword
    (scoped by ``profile.period_months``), up to ``MAX_LIST_PAGES`` list pages
    per keyword. When set, the cap applies to the crawl-total download count.
    """
    if limit is not None and limit < 1:
        raise ValueError("limit must be >= 1")
    download_dir.mkdir(parents=True, exist_ok=True)
    summary = SearchJobSummary()
    stop = should_stop or (lambda: False)
    log = logger
    theme = profile.theme
    period_months = int(profile.period_months or 3)
    keywords = tuple(k.strip() for k in profile.keywords if str(k).strip())
    if not keywords:
        raise ValueError(f"empty keywords for mode: {profile.mode}")

    already = reports_store.downloaded_keys(SOURCE) | reports_store.disk_rpt_ids(
        root=DOWNLOADS_ROOT
    )
    seen: set[str] = set()
    if log:
        log.emit(
            level="info",
            stage="download",
            event="existing_loaded",
            count=len(already),
            keyword_total=len(keywords),
            theme=theme,
            mode=profile.mode,
            period_months=period_months,
            limit=limit,
        )
        log.set_progress(
            limit=limit,
            period_months=period_months,
            downloaded=0,
            listed=0,
            skipped_existing=0,
            existing_known=len(already),
            stage="filter",
            keyword_total=len(keywords),
            theme=theme,
            mode=profile.mode,
        )

    for kw_index, keyword in enumerate(keywords):
        if stop():
            summary.stopped = True
            if log:
                log.emit(
                    level="warn",
                    stage="filter",
                    event="stopped",
                    keyword=keyword,
                    keyword_index=kw_index,
                )
            break
        if limit is not None and len(summary.downloaded) >= limit:
            break

        if log:
            log.emit(
                level="info",
                stage="filter",
                event="keyword_start",
                keyword=keyword,
                keyword_index=kw_index,
                keyword_total=len(keywords),
            )
            log.set_progress(
                stage="filter",
                keyword=keyword,
                keyword_index=kw_index,
                keyword_total=len(keywords),
                period_months=period_months,
                downloaded=len(summary.downloaded),
                listed=summary.listed,
                theme=theme,
                mode=profile.mode,
            )

        try:
            if log:
                with log.stage(
                    "filter",
                    keyword=keyword,
                    keyword_index=kw_index,
                    page_cnt_min=10,
                    theme=theme,
                    mode=profile.mode,
                ):
                    _apply_filters(page, profile=profile, keyword=keyword)
            else:
                _apply_filters(page, profile=profile, keyword=keyword)
        except Exception as exc:
            snap = capture_filter_failure(
                page, download_dir, prefix=f"filter-fail-kw{kw_index}"
            )
            if log:
                log.emit(
                    level="error",
                    stage="filter",
                    event="snapshot",
                    keyword=keyword,
                    keyword_index=kw_index,
                    error=str(exc),
                    **{
                        k: v
                        for k, v in snap.items()
                        if k
                        in (
                            "url",
                            "title",
                            "logged_in",
                            "has_logout",
                            "has_dropdown_text",
                            "has_srchKeyword",
                            "has_srchBtn",
                            "chrome_exit_type",
                            "screenshot",
                            "html",
                            "diag",
                            "screenshot_error",
                            "html_error",
                        )
                    },
                )
            raise
        if touch:
            touch()
        _sort_by_page_count_desc(page)
        if log:
            log.emit(
                level="info",
                stage="filter",
                event="sorted",
                by="page_count_desc",
                keyword=keyword,
            )

        list_page = 0
        prev_page_keys: tuple[str, ...] | None = None
        while (
            (limit is None or len(summary.downloaded) < limit)
            and list_page < MAX_LIST_PAGES
        ):
            if stop():
                summary.stopped = True
                if log:
                    log.emit(
                        level="warn",
                        stage="list",
                        event="stopped",
                        list_page=list_page,
                        keyword=keyword,
                    )
                break
            candidates = [
                c for c in _list_candidates(page) if not _is_short_report(c)
            ]
            page_keys = tuple(
                str(c["rpt_id"]) for c in candidates if c.get("rpt_id")
            )
            if prev_page_keys is not None and page_keys and page_keys == prev_page_keys:
                if log:
                    log.emit(
                        level="warn",
                        stage="list",
                        event="page_stuck",
                        list_page=list_page,
                        keyword=keyword,
                    )
                break
            prev_page_keys = page_keys

            blind_rows = [
                c for c in candidates if c["blind"] and c["rpt_id"] not in seen
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
                    keyword=keyword,
                    keyword_index=kw_index,
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
                    keyword=keyword,
                    keyword_index=kw_index,
                    keyword_total=len(keywords),
                    theme=theme,
                )

            def _attrs_for(
                cand: dict[str, Any], *, blind: bool, kw: str = keyword
            ) -> dict[str, Any]:
                attrs: dict[str, Any] = {
                    "rpt_id": cand["rpt_id"],
                    "provider": cand.get("provider"),
                    "stock": cand.get("stock"),
                    "blind": blind,
                    "keyword": kw,
                    "crawl_profile": theme,
                }
                if theme in REPORT_THEMES:
                    attrs["themes"] = [theme]
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
                            keyword=keyword,
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
                    keyword=keyword,
                    keyword_index=kw_index,
                    keyword_total=len(keywords),
                    theme=theme,
                )

            for cand in blind_rows:
                seen.add(cand["rpt_id"])
                summary.skipped_blind += 1

            for cand in existing_rows:
                seen.add(cand["rpt_id"])
                summary.skipped_existing += 1

            if existing_rows and log:
                log.set_progress(
                    stage="list",
                    listed=summary.listed,
                    skipped_existing=summary.skipped_existing,
                    downloaded=len(summary.downloaded),
                    limit=limit,
                    list_page=list_page,
                    keyword=keyword,
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
                            keyword=keyword,
                        )
                    break
                rpt_id = cand["rpt_id"]
                if rpt_id in seen:
                    continue
                seen.add(rpt_id)
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
                        keyword=keyword,
                        keyword_index=kw_index,
                        keyword_total=len(keywords),
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
                            attrs={
                                "blind": False,
                                "no_custom_download": True,
                                "crawl_profile": theme,
                                "keyword": keyword,
                                **(
                                    {"themes": [theme]}
                                    if theme in REPORT_THEMES
                                    else {}
                                ),
                            },
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
                            keyword=keyword,
                            error=str(exc),
                        )
                        log.set_progress(
                            stage="download",
                            skipped_no_download=summary.skipped_no_download,
                            downloaded=len(summary.downloaded),
                            listed=summary.listed,
                            limit=limit,
                            keyword=keyword,
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
                            attrs={
                                "error": str(exc)[:500],
                                "crawl_profile": theme,
                                "keyword": keyword,
                                **(
                                    {"themes": [theme]}
                                    if theme in REPORT_THEMES
                                    else {}
                                ),
                            },
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
                            keyword=keyword,
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
                            keyword=keyword,
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
                        file_name=path.name,
                        keyword=keyword,
                    )
                    log.set_progress(
                        stage="download",
                        downloaded=len(summary.downloaded),
                        listed=summary.listed,
                        skipped_blind=summary.skipped_blind,
                        skipped_existing=summary.skipped_existing,
                        limit=limit,
                        current_rpt_id=rpt_id,
                        keyword=keyword,
                        keyword_index=kw_index,
                        keyword_total=len(keywords),
                    )
                if touch:
                    touch()
                if limit is not None and len(summary.downloaded) >= limit:
                    break
            if summary.stopped or (
                limit is not None and len(summary.downloaded) >= limit
            ):
                break
            next_ok, next_detail = _goto_next_list_page(page)
            if not next_ok:
                if log:
                    log.emit(
                        level="info",
                        stage="list",
                        event="no_more_pages",
                        list_page=list_page,
                        keyword=keyword,
                        **next_detail,
                    )
                break
            list_page += 1
            if touch:
                touch()

        if log:
            log.emit(
                level="info",
                stage="filter",
                event="keyword_end",
                keyword=keyword,
                keyword_index=kw_index,
                keyword_total=len(keywords),
                downloaded=len(summary.downloaded),
                listed=summary.listed,
            )
        if summary.stopped or (
            limit is not None and len(summary.downloaded) >= limit
        ):
            break

    if log:
        detail = summary.as_detail()
        log.emit(
            level="info",
            stage="download",
            event="crawl_end",
            theme=theme,
            keyword_total=len(keywords),
            **detail,
        )
        log.set_progress(
            stage="done",
            limit=limit,
            period_months=period_months,
            downloaded=detail["downloaded"],
            listed=detail["listed"],
            skipped_blind=detail["skipped_blind"],
            skipped_existing=detail["skipped_existing"],
            skipped_no_download=detail["skipped_no_download"],
            failed=detail["failed"],
            stopped=detail["stopped"],
            keyword_total=len(keywords),
            theme=theme,
            mode=profile.mode,
        )
    return summary


class _NoDownloadError(RuntimeError):
    """Viewer has no #customDownload (typically body-restricted)."""


def _browser_closed_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "has been closed" in msg or "target page, context or browser" in msg


def _wait_search_form(page: Page) -> None:
    """Wait until SearchReport keyword form is interactable."""
    page.locator("#srchKeyword").wait_for(
        state="visible", timeout=FILTER_UI_TIMEOUT_MS
    )
    page.locator("button.dropdown-text").first.wait_for(
        state="visible", timeout=FILTER_UI_TIMEOUT_MS
    )


def _apply_filters_once(
    page: Page, *, profile: SearchProfile, keyword: str
) -> None:
    page.goto(SEARCH_URL, wait_until="domcontentloaded")
    _wait_search_form(page)

    page.locator("button.dropdown-text").first.click(timeout=FILTER_UI_TIMEOUT_MS)
    page.wait_for_timeout(300)
    page.locator("li span.item", has_text="제목").first.click()
    page.wait_for_timeout(300)

    page.locator("#srchKeyword").fill(keyword)
    page.wait_for_timeout(200)

    page.locator("button.select-box.flat-select", has_text="페이지").first.click()
    page.wait_for_timeout(300)
    page.locator("li span.item", has_text=profile.page_min_label).first.click()
    page.wait_for_timeout(300)

    period_label = PERIOD_LABELS.get(profile.period_months, "3개월")
    period = page.locator("#period")
    if period.count():
        try:
            if period.input_value() != str(profile.period_months):
                page.locator("button.select-box.flat-select", has_text="개월").first.click()
                page.wait_for_timeout(200)
                page.locator("li span.item", has_text=period_label).first.click()
                page.wait_for_timeout(200)
        except Exception:
            pass

    if profile.sectors:
        page.locator("#sectorFilterBtn").click()
        page.wait_for_timeout(500)
        for name in profile.sectors:
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


def _apply_filters(
    page: Page, *, profile: SearchProfile, keyword: str
) -> None:
    """Apply SearchReport filters with visible waits and short reload retries."""
    last_exc: BaseException | None = None
    for attempt in range(FILTER_APPLY_RETRIES):
        try:
            _apply_filters_once(page, profile=profile, keyword=keyword)
            return
        except Exception as exc:
            last_exc = exc
            if _browser_closed_error(exc):
                raise
            if attempt + 1 >= FILTER_APPLY_RETRIES:
                raise
            try:
                page.reload(wait_until="domcontentloaded")
            except Exception:
                pass
    assert last_exc is not None
    raise last_exc


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
          const iDate = idxOf('작성일', '날짜', '일자', '등록일', '게시일');
          const iStock = idxOf('종목');
          const iTitle = idxOf('제목');
          const iAuthor = idxOf('작성자');
          const iProvider = idxOf('제공사', '증권사');
          const iPages = idxOf('페이지수', '페이지');
          const dateRe = /(?:20)?\\d{2}[./-]\\d{1,2}[./-]\\d{1,2}/;

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
            let published = cell(iDate, '');
            if (!dateRe.test(published)) {
              published = '';
              for (const t of tds) {
                if (dateRe.test(t)) { published = t; break; }
              }
            }
            if (!published) {
              const rm = rowText.match(dateRe);
              if (rm) published = rm[0];
            }
            out.push({
              rpt_id: m[1],
              href,
              title: norm(a.innerText) || cell(iTitle, ''),
              published_at: published,
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
            m = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", published_raw)
            if not m:
                m2 = re.search(r"\b(\d{2})[./-](\d{1,2})[./-](\d{1,2})\b", published_raw)
                if m2:
                    yy = int(m2.group(1))
                    year = 2000 + yy if yy < 100 else yy
                    published_at = (
                        f"{year}-{int(m2.group(2)):02d}-{int(m2.group(3)):02d}"
                    )
            else:
                published_at = (
                    f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                )
            if published_at is None:
                m3 = re.search(r"(20\d{2})(\d{2})(\d{2})", published_raw)
                if m3:
                    published_at = (
                        f"{m3.group(1)}-{m3.group(2)}-{m3.group(3)}"
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


def _is_short_report(cand: dict[str, Any]) -> bool:
    """True when page_count is known and at or below the keep threshold."""
    page_count = cand.get("page_count")
    if page_count is None:
        return False
    try:
        return int(page_count) <= MIN_PAGE_COUNT
    except (TypeError, ValueError):
        return False


def _goto_next_list_page(page: Page) -> tuple[bool, dict[str, Any]]:
    """Advance SearchReport list pagination. Returns (ok, detail)."""
    detail: dict[str, Any] = {}
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
        name = _download_filename(
            index=index, rpt_id=rpt_id, title=title, suggested=suggested
        )
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


def _download_filename(
    *,
    index: int,
    rpt_id: str,
    title: str,
    suggested: str,
    max_name_bytes: int = 180,
) -> str:
    """Short name: NN-rptId-titleHead.ext (avoid ENAMETOOLONG)."""
    ext = Path(suggested).suffix.lower()
    if ext not in {".pdf", ".zip", ".hwp", ".hwpx"}:
        ext = ".pdf"
    prefix = f"{index:02d}-{rpt_id}-"
    budget = max_name_bytes - len(prefix.encode("utf-8")) - len(ext.encode("utf-8"))
    if budget < 0:
        return f"{index:02d}-{rpt_id}{ext}"

    safe = re.sub(r"[^\w\-가-힣]+", "_", title or "").strip("_")
    # Prefer a short head; also hard-cap by UTF-8 bytes for Linux NAME_MAX.
    head = safe[:40]
    while head and len(head.encode("utf-8")) > budget:
        head = head[:-1]
    head = head.strip("_")
    if not head:
        return f"{index:02d}-{rpt_id}{ext}"
    return f"{prefix}{head}{ext}"
