"""BCG Featured Insights / industry surfaces via one Patchright browser.

List URLs are allowlisted per desk-theme profile (probe-confirmed only).
Never invent ``/publications/{year}/{slug}`` article URLs.
"""

from __future__ import annotations

import calendar
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from patchright.sync_api import Page

SOURCE = "bcg"
HUB_URL = "https://www.bcg.com/"
LIST_URL = "https://www.bcg.com/publications"
BASE = "https://www.bcg.com"
DEFAULT_PROFILE = "report"


@dataclass(frozen=True)
class BcgProfile:
    """Desk theme → confirmed list surfaces (no guessed article URLs)."""

    id: str
    label: str
    list_urls: tuple[str, ...]
    period_months: int = 3


# Surfaces confirmed via adhoc/self probe (2026-08-01). Empty list_urls = disabled.
PROFILES: dict[str, BcgProfile] = {
    "report": BcgProfile(
        id="report",
        label="Featured Insights",
        list_urls=(LIST_URL,),
    ),
    "ai": BcgProfile(
        id="ai",
        label="AI",
        list_urls=(
            "https://www.bcg.com/capabilities/artificial-intelligence",
            "https://www.bcg.com/capabilities/artificial-intelligence/generative-ai",
        ),
    ),
    "datacenter": BcgProfile(
        id="datacenter",
        label="데이터센터",
        list_urls=(
            "https://www.bcg.com/capabilities/digital-technology-data/cloud-computing",
            "https://www.bcg.com/industries/energy/power-utilities",
            "https://www.bcg.com/industries/technology-media-telecommunications/semiconductors",
        ),
    ),
    "physical_ai": BcgProfile(
        id="physical_ai",
        label="피지컬 AI",
        list_urls=(
            "https://www.bcg.com/capabilities/manufacturing/industry-4.0",
            "https://www.bcg.com/industries/industrial-goods/machinery-industrial-automation",
        ),
    ),
    "appliance": BcgProfile(
        id="appliance",
        label="가전",
        list_urls=(
            "https://www.bcg.com/industries/consumer-products-industry/overview",
        ),
    ),
    "display": BcgProfile(
        id="display",
        label="디스플레이",
        list_urls=(
            "https://www.bcg.com/industries/technology-media-telecommunications/future-of-television",
            "https://www.bcg.com/industries/technology-media-telecommunications/technology-industry",
        ),
    ),
    "automotive": BcgProfile(
        id="automotive",
        label="자동차",
        list_urls=("https://www.bcg.com/industries/automotive/overview",),
    ),
    "petrochemical": BcgProfile(
        id="petrochemical",
        label="석유화학",
        list_urls=(
            "https://www.bcg.com/industries/industrial-goods/chemicals",
        ),
    ),
}

PROFILE_IDS = frozenset(PROFILES)


def get_profile(profile_id: str | None = None) -> BcgProfile:
    key = (profile_id or DEFAULT_PROFILE).strip().lower() or DEFAULT_PROFILE
    prof = PROFILES.get(key)
    if prof is None:
        raise ValueError(
            f"unknown BCG profile {profile_id!r}; "
            f"expected one of: {', '.join(sorted(PROFILES))}"
        )
    if not prof.list_urls:
        raise ValueError(
            f"BCG profile {key!r} has no confirmed list_urls "
            "(run bcg_adhoc_probe / update allowlist)"
        )
    return prof


def normalize_list_url(url: str) -> str:
    path = urlparse(url or "").path.rstrip("/") or "/"
    return f"{BASE}{path}".lower()


def is_allowlisted_list_url(url: str, profile: BcgProfile) -> bool:
    n = normalize_list_url(url)
    return n in {normalize_list_url(u) for u in profile.list_urls}


def is_publications_hub(url: str) -> bool:
    return bool(re.search(r"/publications/?$", urlparse(url or "").path or "", re.I))


_DENIED_RE = re.compile(
    r"access\s*denied|errors\.edgesuite|reference\s*#",
    re.I,
)
_DATE_RE = re.compile(
    r"\b("
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?"
    r")\s+(\d{1,2}),?\s+(\d{4})\b",
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
_ARTICLE_PATH_RE = re.compile(
    r"/publications/(\d{4})/([a-z0-9-]+)/?$",
    re.I,
)


class BcgCaptureError(RuntimeError):
    pass


class BcgBlockedError(BcgCaptureError):
    """Access Denied / empty — must not mark downloaded."""


@dataclass(frozen=True)
class BcgListItem:
    source_key: str
    url: str
    title: str
    published_at: date | None
    publish_date_raw: str


def months_ago_cutoff(months: int, *, now: datetime | None = None) -> date:
    ref = now or datetime.now()
    y, m = ref.year, ref.month - int(months)
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def parse_bcg_date(text: str) -> date | None:
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
    m = _ARTICLE_PATH_RE.search(path)
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2)}"


def source_key_from_url(url: str) -> str:
    return slug_from_url(url) or (url or "")[-240:]


def is_publication_article_url(url: str) -> bool:
    return slug_from_url(url) is not None


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


def warmup_hub(page: Page) -> None:
    page.goto(HUB_URL, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(1500)
    if _page_blocked(page.evaluate("() => (document.body?.innerText||'')") or ""):
        raise BcgBlockedError(f"access denied at hub {page.url}")
    accept_cookies_if_visible(page)


def open_list_url(page: Page, list_url: str) -> None:
    """Open an allowlisted list surface (caller must validate URL)."""
    page.goto(list_url, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(2500)
    try:
        page.wait_for_load_state("networkidle", timeout=30_000)
    except Exception:
        pass
    page.wait_for_timeout(1500)
    accept_cookies_if_visible(page)
    body = page.evaluate("() => (document.body?.innerText||'')") or ""
    if _page_blocked(body) or len(body) < 80:
        raise BcgBlockedError(f"access denied or empty list {page.url}")


def warmup_and_open_list(page: Page, list_url: str = LIST_URL) -> None:
    warmup_hub(page)
    open_list_url(page, list_url)


def _page_blocked(text: str) -> bool:
    return bool(_DENIED_RE.search(text or ""))


def collect_list_items(page: Page) -> list[BcgListItem]:
    raw = page.evaluate(
        """() => {
          const out = [];
          const seen = new Set();
          for (const a of document.querySelectorAll('a[href*="/publications/"]')) {
            const href = (a.href || '').split('#')[0].split('?')[0];
            if (!href || seen.has(href)) continue;
            if (!/bcg\\.com/i.test(href)) continue;
            if (!/\\/publications\\/\\d{4}\\/[a-z0-9-]+\\/?$/i.test(
              new URL(href).pathname
            )) continue;
            const title = (a.innerText || '').trim().replace(/\\s+/g, ' ');
            if (title.length < 12) continue;
            let dateRaw = '';
            let root = a.parentElement;
            for (let i = 0; i < 8 && root; i++) {
              const t = root.innerText || '';
              const m = t.match(
                /\\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\\s+\\d{1,2},?\\s+\\d{4}\\b/i
              );
              if (m) { dateRaw = m[0]; break; }
              root = root.parentElement;
            }
            seen.add(href);
            out.push({ href, title: title.slice(0, 300), date_raw: dateRaw });
            if (out.length >= 40) break;
          }
          return out;
        }"""
    )
    items: list[BcgListItem] = []
    for row in raw or []:
        url = str(row.get("href") or "")
        key = slug_from_url(url)
        if not key:
            continue
        date_raw = str(row.get("date_raw") or "")
        items.append(
            BcgListItem(
                source_key=key,
                url=url,
                title=str(row.get("title") or key),
                published_at=parse_bcg_date(date_raw),
                publish_date_raw=date_raw,
            )
        )
    return items


def click_load_more(page: Page) -> bool:
    """Click Load More only if a clear control is visible (not confirmed on site)."""
    loc = page.locator(
        "button, a[role='button'], a.btn, [class*='load-more']",
        has_text=re.compile(r"^\s*Load More\s*$", re.I),
    )
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
          return {
            url: location.href,
            title: (document.title || '').trim(),
            h1: (document.querySelector('h1')?.innerText || '').trim(),
            main_len: main.length,
            body_sample: main.slice(0, 500),
            pdf_hrefs: [...new Set(pdfs)].slice(0, 5),
            date_raw: (timeEl && (timeEl.getAttribute('datetime') || timeEl.innerText)) || '',
          };
        }"""
    )


def open_publication(
    page: Page, url: str, *, referer: str = LIST_URL
) -> None:
    """Prefer click from current list; else goto with list referer."""
    if not is_publication_article_url(url):
        raise BcgCaptureError(f"not a publications article URL: {url}")
    slug = (slug_from_url(url) or "").split("/")[-1]
    if slug:
        loc = page.locator(f'a[href*="{slug}"]').filter(
            has_text=re.compile(r".{12,}")
        )
        try:
            if loc.count() and loc.first.is_visible(timeout=1500):
                loc.first.scroll_into_view_if_needed(timeout=3000)
                loc.first.click(timeout=10_000)
                page.wait_for_timeout(2500)
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=30_000)
                except Exception:
                    pass
                return
        except Exception:
            pass
    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=90_000,
        referer=referer,
    )
    page.wait_for_timeout(2500)


def capture_insight(
    page: Page,
    url: str,
    dest: Path,
    *,
    referer: str = LIST_URL,
    min_body_chars: int = 400,
    min_pdf_bytes: int = 1000,
) -> dict[str, Any]:
    """Open one publication; PDF or gated page.pdf. Never save Access Denied."""
    open_publication(page, url, referer=referer)
    accept_cookies_if_visible(page)
    try:
        page.wait_for_load_state("networkidle", timeout=30_000)
    except Exception:
        pass
    page.wait_for_timeout(1000)
    sig = _detail_signals(page)
    sample = str(sig.get("body_sample") or "")
    if _page_blocked(sample) or _page_blocked(page.content() or ""):
        raise BcgBlockedError(f"access denied at {url}")
    if _page_blocked(str(sig.get("title") or "")) or _page_blocked(
        str(sig.get("h1") or "")
    ):
        raise BcgBlockedError(f"access denied title at {url}")
    main_len = int(sig.get("main_len") or 0)
    if main_len < min_body_chars:
        raise BcgBlockedError(f"empty/thin body at {url} (len={main_len})")

    dest.parent.mkdir(parents=True, exist_ok=True)
    pdf_hrefs = list(sig.get("pdf_hrefs") or [])
    if pdf_hrefs:
        href = pdf_hrefs[0]
        resp = page.context.request.get(href, timeout=120_000)
        body = resp.body()
        if resp.status >= 400:
            raise BcgCaptureError(f"pdf http {resp.status} for {href}")
        if len(body) < min_pdf_bytes or not body[:5].startswith(b"%PDF"):
            text_head = body[:2000].decode("utf-8", errors="ignore")
            if _page_blocked(text_head):
                raise BcgBlockedError(f"pdf blocked at {href}")
            raise BcgCaptureError(
                f"pdf not valid ({len(body)} bytes, status={resp.status})"
            )
        dest.write_bytes(body)
        text = _pdftotext_sample(dest)
        if _page_blocked(text):
            dest.unlink(missing_ok=True)
            raise BcgBlockedError(f"access denied inside pdf {href}")
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
        raise BcgCaptureError(f"page.pdf too small: {dest}")
    text = _pdftotext_sample(dest)
    if _page_blocked(text):
        dest.unlink(missing_ok=True)
        raise BcgBlockedError(f"access denied in page.pdf for {url}")
    return {
        "bytes": dest.stat().st_size,
        "body_len": main_len,
        "title": sig.get("h1") or sig.get("title"),
        "capture": "page.pdf",
        "date_raw": sig.get("date_raw") or "",
        "pdf_text_len": len(text.strip()),
    }
