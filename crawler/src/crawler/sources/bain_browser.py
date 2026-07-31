"""Bain Insights list + detail capture via one Patchright browser (no HTTP spray)."""

from __future__ import annotations

import calendar
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from patchright.sync_api import Page

SOURCE = "bain"
HUB_URL = "https://www.bain.com/"
LIST_URL = "https://www.bain.com/insights/"
BASE = "https://www.bain.com"

# Confirmed hub-only paths under /insights/ (not articles).
_HUB_SLUGS = frozenset(
    {
        "industry-insights",
        "consulting-services-insights",
        "featured-topics",
        "topics",
    }
)

_DENIED_RE = re.compile(
    r"access\s*denied|errors\.edgesuite|reference\s*#",
    re.I,
)
_DATE_RE = re.compile(
    r"\b("
    r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
    r")[a-z]*\s+(\d{1,2}),?\s+(\d{4})\b",
    re.I,
)
_MONTHS = {
    name.lower(): i
    for i, name in enumerate(calendar.month_abbr)
    if name
} | {
    name.lower(): i
    for i, name in enumerate(calendar.month_name)
    if name
}


class BainCaptureError(RuntimeError):
    """Detail/PDF capture failed or blocked."""


class BainBlockedError(BainCaptureError):
    """Access Denied / empty gate — must not mark downloaded."""


@dataclass(frozen=True)
class BainListItem:
    source_key: str
    url: str
    title: str
    published_at: date | None
    publish_date_raw: str
    content_type: str | None


def months_ago_cutoff(months: int, *, now: datetime | None = None) -> date:
    ref = now or datetime.now()
    y, m = ref.year, ref.month - int(months)
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def parse_bain_date(text: str) -> date | None:
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    mon = _MONTHS.get(m.group(1).lower()[:3]) or _MONTHS.get(m.group(1).lower())
    if not mon:
        return None
    try:
        return date(int(m.group(3)), int(mon), int(m.group(2)))
    except ValueError:
        return None


def slug_from_url(url: str) -> str | None:
    path = urlparse(url or "").path.rstrip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) != 2 or parts[0] != "insights":
        return None
    slug = parts[1]
    if slug in _HUB_SLUGS:
        return None
    return slug


def source_key_from_url(url: str) -> str:
    return slug_from_url(url) or (url or "")[-240:]


def accept_cookies_if_visible(page: Page) -> bool:
    for sel in (
        "#onetrust-accept-btn-handler",
        "button:has-text('Accept All')",
        "button:has-text('Accept')",
    ):
        loc = page.locator(sel).first
        try:
            if loc.count() and loc.is_visible(timeout=800):
                loc.click(timeout=2000)
                page.wait_for_timeout(600)
                return True
        except Exception:
            continue
    return False


def warmup_and_open_list(page: Page) -> None:
    """Hub (optional cookies) → confirmed Insights list URL."""
    page.goto(HUB_URL, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(1500)
    accept_cookies_if_visible(page)
    page.goto(LIST_URL, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(2500)
    accept_cookies_if_visible(page)
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    page.wait_for_timeout(400)


def open_list(page: Page) -> None:
    page.goto(LIST_URL, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(2500)
    accept_cookies_if_visible(page)
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass


def _page_blocked(text: str) -> bool:
    return bool(_DENIED_RE.search(text or ""))


def collect_list_items(page: Page) -> list[BainListItem]:
    """Collect article cards from main feed (excludes site-search suggestions)."""
    raw = page.evaluate(
        """() => {
          const main = document.querySelector('main') || document.body;
          const out = [];
          const seen = new Set();
          const cards = [
            ...main.querySelectorAll('div.card.card--insights'),
            ...main.querySelectorAll('ul.insights-list__list > li'),
          ];
          for (const card of cards) {
            if (card.closest('.site-search, form.site-search__search-form, [class*="site-search"]')) {
              continue;
            }
            const a = card.querySelector('a[href*="/insights/"]');
            if (!a) continue;
            const href = (a.href || '').split('#')[0];
            if (!href || seen.has(href)) continue;
            const path = new URL(href).pathname.replace(/\\/$/, '');
            const parts = path.split('/').filter(Boolean);
            if (parts[0] !== 'insights' || parts.length !== 2) continue;
            const slug = parts[1];
            if (/^(industry-insights|consulting-services-insights|featured-topics|topics)$/i.test(slug)) {
              continue;
            }
            let title = '';
            const h = card.querySelector(
              'h2 a, h3 a, h4 a, h2, h3, h4, .insights-list__text-container h4 a'
            );
            if (h) title = (h.innerText || '').trim().replace(/\\s+/g, ' ');
            if (!title) {
              const wrap = card.querySelector('.card__wrapper[data-url]');
              // Prefer primary content link text over tag/desc blurbs.
              const primary = card.querySelector('.card__content a[href*="/insights/"]')
                || a;
              title = (primary.innerText || '').trim().replace(/\\s+/g, ' ');
              // Drop leading topic tags if duplicated in long blurb
              if (title.length > 120) {
                const lines = title.split(/(?<=[.!?])\\s+/);
                title = (lines[0] || title).slice(0, 200);
              }
              void wrap;
            }
            if (title.length < 8) continue;
            const dateEl = card.querySelector('span.date-format');
            const dateRaw = dateEl ? (dateEl.innerText || '').trim() : '';
            const typeEl = card.querySelector(
              'p.insights-list__content-type, .card__tag, [class*="content-type"]'
            );
            let contentType = typeEl ? (typeEl.innerText || '').trim() : '';
            if (!contentType) {
              const m = (card.innerText || '').match(
                /\\b(Brief|Report|Article|Podcast|Video|Book|Interactive)\\b/
              );
              contentType = m ? m[1] : '';
            }
            seen.add(href);
            out.push({
              href,
              title: title.slice(0, 300),
              date_raw: dateRaw,
              content_type: contentType || null,
            });
          }
          return out;
        }"""
    )
    items: list[BainListItem] = []
    for row in raw or []:
        url = str(row.get("href") or "")
        slug = slug_from_url(url)
        if not slug:
            continue
        date_raw = str(row.get("date_raw") or "")
        items.append(
            BainListItem(
                source_key=slug,
                url=url if url.startswith("http") else urljoin(BASE, url),
                title=str(row.get("title") or slug),
                published_at=parse_bain_date(date_raw),
                publish_date_raw=date_raw,
                content_type=row.get("content_type"),
            )
        )
    return items


def click_load_more(page: Page) -> bool:
    """Click confirmed LOAD MORE control if visible. Returns True if clicked."""
    loc = page.locator("a.btn.btn--cta", has_text=re.compile(r"^\s*LOAD MORE\s*$", re.I))
    try:
        if not loc.count():
            return False
        first = loc.first
        if not first.is_visible(timeout=1500):
            return False
        first.scroll_into_view_if_needed(timeout=3000)
        first.click(timeout=5000)
        page.wait_for_timeout(3000)
        return True
    except Exception:
        return False


def pdf_page_count(path: Path | str) -> int | None:
    p = Path(path)
    if not p.is_file() or shutil.which("pdfinfo") is None:
        return None
    proc = subprocess.run(
        ["pdfinfo", str(p)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    for line in (proc.stdout or "").splitlines():
        if line.lower().startswith("pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def _pdftotext_sample(path: Path, *, max_pages: int = 2) -> str:
    if shutil.which("pdftotext") is None:
        return ""
    proc = subprocess.run(
        ["pdftotext", "-f", "1", "-l", str(max_pages), str(path), "-"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return proc.stdout or ""


def _detail_signals(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const pick = (sel) => {
            const el = document.querySelector(sel);
            return el ? (el.innerText || '').trim() : '';
          };
          const main = pick('main') || pick('article') || pick('[role=main]')
            || (document.body ? (document.body.innerText || '').trim() : '');
          const pdfs = [...document.querySelectorAll('a[href*=".pdf"]')]
            .map(a => a.href)
            .filter(h => /\\.pdf(\\?|$)/i.test(h));
          const timeEl = document.querySelector('time');
          const dateEl = document.querySelector('span.date-format');
          return {
            url: location.href,
            title: (document.title || '').trim(),
            h1: (document.querySelector('h1')?.innerText || '').trim(),
            main_len: main.length,
            body_sample: main.slice(0, 400),
            pdf_hrefs: [...new Set(pdfs)].slice(0, 5),
            date_raw: (timeEl && (timeEl.getAttribute('datetime') || timeEl.innerText))
              || (dateEl && dateEl.innerText) || '',
          };
        }"""
    )


def capture_insight(
    page: Page,
    url: str,
    dest: Path,
    *,
    min_body_chars: int = 400,
    min_pdf_bytes: int = 1000,
) -> dict[str, Any]:
    """Open one insight URL and save PDF href or gated page.pdf.

    Never marks Access Denied / empty body as success.
    """
    page.goto(url, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(2000)
    accept_cookies_if_visible(page)
    sig = _detail_signals(page)
    if _page_blocked(sig.get("body_sample") or "") or _page_blocked(
        page.content() or ""
    ):
        raise BainBlockedError(f"access denied at {url}")
    main_len = int(sig.get("main_len") or 0)
    if main_len < min_body_chars:
        raise BainBlockedError(f"empty/thin body at {url} (len={main_len})")

    dest.parent.mkdir(parents=True, exist_ok=True)
    pdf_hrefs = list(sig.get("pdf_hrefs") or [])
    if pdf_hrefs:
        href = pdf_hrefs[0]
        resp = page.context.request.get(href, timeout=120_000)
        body = resp.body()
        if resp.status >= 400:
            raise BainCaptureError(f"pdf http {resp.status} for {href}")
        if len(body) < min_pdf_bytes or not body[:5].startswith(b"%PDF"):
            text_head = body[:2000].decode("utf-8", errors="ignore")
            if _page_blocked(text_head):
                raise BainBlockedError(f"pdf blocked at {href}")
            raise BainCaptureError(
                f"pdf not valid ({len(body)} bytes, status={resp.status})"
            )
        dest.write_bytes(body)
        sample = _pdftotext_sample(dest)
        if _page_blocked(sample):
            dest.unlink(missing_ok=True)
            raise BainBlockedError(f"access denied inside pdf {href}")
        return {
            "bytes": dest.stat().st_size,
            "body_len": main_len,
            "title": sig.get("h1") or sig.get("title"),
            "capture": "pdf_href",
            "pdf_href": href,
            "date_raw": sig.get("date_raw") or "",
        }

    page.pdf(path=str(dest), format="A4", print_background=True)
    if not dest.is_file() or dest.stat().st_size < min_pdf_bytes:
        raise BainCaptureError(f"page.pdf too small: {dest}")
    sample = _pdftotext_sample(dest)
    if _page_blocked(sample):
        dest.unlink(missing_ok=True)
        raise BainBlockedError(f"access denied in page.pdf for {url}")
    return {
        "bytes": dest.stat().st_size,
        "body_len": main_len,
        "title": sig.get("h1") or sig.get("title"),
        "capture": "page.pdf",
        "date_raw": sig.get("date_raw") or "",
        "pdf_text_len": len(sample.strip()),
    }
