"""HBR.org Latest list + gated page.pdf via logged-in Patchright page."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from patchright.sync_api import Page

SOURCE = "hbr"
HUB_URL = "https://hbr.org/"
LATEST_URL = "https://hbr.org/the-latest"
BASE = "https://hbr.org"

ARTICLE_RE = re.compile(
    r"^https?://(?:www\.)?hbr\.org/(\d{4})/(\d{2})/([a-z0-9-]+)/?(?:[?#].*)?$",
    re.I,
)
_DENIED_RE = re.compile(
    r"access\s*denied|errors\.edgesuite|reference\s*#",
    re.I,
)
_PAYWALL_RE = re.compile(
    r"subscribe\s+to\s+read|already a subscriber|sign in to read|"
    r"member[-\s]?only|unlock this|hbr executive",
    re.I,
)


class HbrCaptureError(RuntimeError):
    pass


class HbrBlockedError(HbrCaptureError):
    """Paywall / empty / denied — must not mark downloaded."""

    def __init__(self, message: str, *, title: str | None = None) -> None:
        super().__init__(message)
        self.title = (title or "").strip() or None


@dataclass(frozen=True)
class HbrListItem:
    source_key: str
    url: str
    title: str
    published_at: date | None
    publish_date_raw: str


_WEAK_LINK_TITLE_RE = re.compile(
    r"^(read more|more|continue|see more|view)$",
    re.I,
)


def title_from_slug(slug: str) -> str:
    """Humanize a URL slug for list/detail fallback titles."""
    text = re.sub(r"[-_]+", " ", (slug or "").strip())
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300] if text else slug


def is_weak_link_title(title: str) -> bool:
    t = (title or "").strip()
    if len(t) < 4:
        return True
    return bool(_WEAK_LINK_TITLE_RE.match(t))


def months_ago_cutoff(months: int, *, now: datetime | None = None) -> date:
    ref = now or datetime.now()
    y, m = ref.year, ref.month - int(months)
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def parse_article_url(url: str) -> tuple[str, date | None] | None:
    m = ARTICLE_RE.match((url or "").strip())
    if not m:
        return None
    y, mo, slug = int(m.group(1)), int(m.group(2)), m.group(3)
    try:
        pub = date(y, mo, 1)
    except ValueError:
        pub = None
    return slug, pub


def source_key_from_url(url: str) -> str:
    parsed = parse_article_url(url)
    if parsed:
        return parsed[0]
    return (url or "")[-240:]


def open_latest(page: Page) -> None:
    page.goto(LATEST_URL, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(2500)


def collect_list_items(page: Page) -> list[HbrListItem]:
    # Dates may live on a magazine package ancestor — use that only for dateRaw.
    # Titles must stay card-local: never querySelector on dateRoot (package hed
    # would copy onto every article in the issue).
    raw = page.evaluate(
        """() => {
          const DATE_RE = /\\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\\s+\\d{1,2},\\s+\\d{4}\\b/;
          const WEAK_TITLE = /^(read more|more|continue|see more|view)$/i;
          const ARTICLE_HREF = /hbr\\.org\\/\\d{4}\\/\\d{2}\\/[a-z0-9-]+\\/?$/i;
          const out = [];
          const seen = new Set();
          for (const a of document.querySelectorAll('a[href*="/20"]')) {
            const href = (a.href || '').split('#')[0].split('?')[0];
            if (!ARTICLE_HREF.test(href)) continue;
            if (seen.has(href)) continue;
            seen.add(href);
            let dateRaw = '';
            let el = a.parentElement;
            for (let i = 0; i < 8 && el; i++) {
              const m = (el.innerText || '').match(DATE_RE);
              if (m) { dateRaw = m[0]; break; }
              el = el.parentElement;
            }
            let title = (a.innerText || '').trim().replace(/\\s+/g, ' ');
            if (title.length < 4 || WEAK_TITLE.test(title)) {
              title = '';
              let node = a.parentElement;
              for (let i = 0; i < 6 && node; i++) {
                const links = [...node.querySelectorAll('a[href*="/20"]')]
                  .filter((x) => ARTICLE_HREF.test((x.href || '').split('#')[0]));
                if (links.length >= 1 && links.length <= 2) {
                  const heading = node.querySelector('h2, h3, h4');
                  const hed = (heading && heading.innerText || '').trim().replace(/\\s+/g, ' ');
                  if (hed.length >= 4 && !WEAK_TITLE.test(hed)) {
                    title = hed;
                    break;
                  }
                }
                if (links.length > 2) break;
                node = node.parentElement;
              }
            }
            if (!title) {
              const parts = href.split('/').filter(Boolean);
              title = (parts[parts.length - 1] || '').replace(/-/g, ' ');
            }
            out.push({
              href,
              title: title.slice(0, 300),
              date_raw: dateRaw,
            });
            if (out.length >= 400) break;
          }
          return out;
        }"""
    )
    items: list[HbrListItem] = []
    for row in raw or []:
        url = str(row.get("href") or "")
        parsed = parse_article_url(url)
        if not parsed:
            continue
        slug, ym = parsed
        date_raw = str(row.get("date_raw") or "")
        published = parse_publish_date(date_raw) or ym
        raw_title = str(row.get("title") or "").strip()
        if is_weak_link_title(raw_title):
            raw_title = title_from_slug(slug)
        items.append(
            HbrListItem(
                source_key=slug,
                url=url if url.startswith("http") else f"{BASE}{url}",
                title=raw_title or title_from_slug(slug),
                published_at=published,
                publish_date_raw=date_raw or (ym.isoformat() if ym else ""),
            )
        )
    return items


def _parse_long_date(text: str) -> date | None:
    m = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+(\d{1,2}),\s+(\d{4})\b",
        text or "",
        re.I,
    )
    if not m:
        return None
    months = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }
    mo = months.get(m.group(1).lower())
    if not mo:
        return None
    try:
        return date(int(m.group(3)), mo, int(m.group(2)))
    except ValueError:
        return None


def parse_publish_date(text: str) -> date | None:
    """Parse HBR list/detail date text or ISO ``YYYY-MM-DD`` / datetime."""
    raw = (text or "").strip()
    if not raw:
        return None
    parsed = _parse_long_date(raw)
    if parsed:
        return parsed
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def click_load_more(page: Page) -> bool:
    """Click Latest 'Load More Items'; scroll into view first."""
    loc = page.get_by_text(re.compile(r"^\s*Load More Items\s*$", re.I))
    try:
        if not loc.count():
            return False
        btn = loc.first
        try:
            btn.scroll_into_view_if_needed(timeout=5000)
        except Exception:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(800)
        if not btn.is_visible(timeout=2500):
            return False
        btn.click(timeout=8000)
        page.wait_for_timeout(3500)
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


def capture_article_pdf(
    page: Page,
    url: str,
    dest: Path,
    *,
    min_body_chars: int = 800,
    min_pdf_bytes: int = 1000,
) -> dict[str, Any]:
    """Open one article; page.pdf only when logged-in body clears paywall gate."""
    page.goto(url, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(2500)
    sig = page.evaluate(
        """() => {
          const main = (document.querySelector('article')?.innerText
            || document.querySelector('main')?.innerText
            || document.body?.innerText || '').trim();
          // Piano leaves a hidden paywall mount in DOM after login — ignore invisible nodes.
          const paywallEl = [...document.querySelectorAll(
            '[class*=paywall], [class*=Paywall], [id*=paywall]'
          )].some((el) => {
            const cls = String(el.className || '');
            if (/__hidden|\\bhidden\\b/i.test(cls)) return false;
            const st = getComputedStyle(el);
            if (st.display === 'none' || st.visibility === 'hidden' || Number(st.opacity) === 0) {
              return false;
            }
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
          });
          const pdfs = [...document.querySelectorAll('a[href*=".pdf"]')]
            .map(a => a.href).filter(h => /\\.pdf(\\?|$)/i.test(h));
          const DATE_RE = /\\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\\s+\\d{1,2},\\s+\\d{4}\\b/;
          const timeEl = document.querySelector('time');
          const metaPub = document.querySelector(
            'meta[property="article:published_time"], meta[name="article:published_time"], meta[property="og:updated_time"]'
          );
          const ld = [...document.querySelectorAll('script[type="application/ld+json"]')]
            .map((el) => el.textContent || '').join('\\n');
          const ldMatch = ld.match(/"datePublished"\\s*:\\s*"([^"]+)"/);
          const byline = (main.slice(0, 800).match(DATE_RE) || [])[0] || '';
          const dateRaw = (
            (timeEl && (timeEl.getAttribute('datetime') || timeEl.innerText))
            || (metaPub && metaPub.getAttribute('content'))
            || (ldMatch && ldMatch[1])
            || byline
            || ''
          ).trim();
          const og = document.querySelector('meta[property="og:title"]');
          const title = (
            document.querySelector('h1')?.innerText
            || (og && og.getAttribute('content'))
            || document.title
            || ''
          ).trim();
          return {
            url: location.href,
            title,
            main_len: main.length,
            sample: main.slice(0, 500),
            paywallEl,
            pdfs: pdfs.slice(0, 5),
            date_raw: dateRaw,
          };
        }"""
    )
    detail_title = str(sig.get("title") or "").strip() or None
    sample = str(sig.get("sample") or "")
    if _DENIED_RE.search(sample) or _DENIED_RE.search(page.content() or ""):
        raise HbrBlockedError(f"access denied at {url}", title=detail_title)
    if sig.get("paywallEl") or _PAYWALL_RE.search(sample):
        raise HbrBlockedError(f"paywall at {url}", title=detail_title)
    main_len = int(sig.get("main_len") or 0)
    if main_len < min_body_chars:
        raise HbrBlockedError(
            f"thin body at {url} (len={main_len})",
            title=detail_title,
        )

    date_raw = str(sig.get("date_raw") or "").strip()
    published = parse_publish_date(date_raw)

    dest.parent.mkdir(parents=True, exist_ok=True)
    pdf_hrefs = list(sig.get("pdfs") or [])
    if pdf_hrefs:
        href = pdf_hrefs[0]
        resp = page.context.request.get(href, timeout=120_000)
        body = resp.body()
        if resp.status >= 400 or len(body) < min_pdf_bytes or not body[:5].startswith(
            b"%PDF"
        ):
            raise HbrCaptureError(f"pdf download failed status={resp.status}")
        dest.write_bytes(body)
        return {
            "bytes": dest.stat().st_size,
            "body_len": main_len,
            "title": sig.get("title"),
            "capture": "pdf_href",
            "pdf_href": href,
            "date_raw": date_raw,
            "published_at": published,
        }

    page.pdf(path=str(dest), format="A4", print_background=True)
    if not dest.is_file() or dest.stat().st_size < min_pdf_bytes:
        raise HbrCaptureError(f"page.pdf too small: {dest}")
    if shutil.which("pdftotext"):
        proc = subprocess.run(
            ["pdftotext", "-f", "1", "-l", "2", str(dest), "-"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        txt = proc.stdout or ""
        if _DENIED_RE.search(txt) or _PAYWALL_RE.search(txt[:800]):
            dest.unlink(missing_ok=True)
            raise HbrBlockedError(
                f"paywall/denied in page.pdf for {url}",
                title=detail_title,
            )
        if not published:
            published = parse_publish_date(txt[:1200])
            if published and not date_raw:
                date_raw = published.isoformat()
    return {
        "bytes": dest.stat().st_size,
        "body_len": main_len,
        "title": sig.get("title"),
        "capture": "page.pdf",
        "date_raw": date_raw,
        "published_at": published,
    }
