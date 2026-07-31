"""HBR Korea list + page.pdf capture via logged-in Playwright page."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from patchright.sync_api import Page

SOURCE = "hbrkorea"
BASE = "https://www.hbrkorea.com"
LATEST_URL = f"{BASE}/article/latest"

DATE_RE = re.compile(r"(\d{4})\.\s*(\d{1,2})(?:\.\s*(\d{1,2}))?")
ISSUE_RE = re.compile(r"(\d{4})\.\s*(\d{1,2})-(\d{1,2})월호")
ARTICLE_NO_RE = re.compile(r"article_no/(\d+)")


@dataclass(frozen=True)
class HbrListItem:
    source_key: str
    url: str
    title: str
    published_at: date | None
    publish_date_raw: str
    post_type: str
    article_no: str
    atype: str | None


def months_ago_cutoff(months: int, *, now: datetime | None = None) -> date:
    ref = now or datetime.now()
    y, m = ref.year, ref.month - int(months)
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def parse_post_ho(text: str) -> date | None:
    """Parse ``2026. 7. 31.`` or magazine ``2026. 7-8월호`` → date."""
    text = (text or "").strip()
    m = ISSUE_RE.search(text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), 1)
    m = DATE_RE.search(text)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3) or 1))
    except ValueError:
        return None


def article_no_from_url(url: str) -> str | None:
    m = ARTICLE_NO_RE.search(url or "")
    return m.group(1) if m else None


def atype_from_url(url: str) -> str | None:
    m = re.search(r"/atype/(di|ma)/", url or "")
    return m.group(1) if m else None


def source_key_from_url(url: str) -> str:
    no = article_no_from_url(url)
    if no:
        return no
    return (url or "")[-240:]


def _goto(page: Page, url: str) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(600)


def open_list_page(page: Page, page_num: int) -> None:
    """Navigate to latest list page ``page_num`` (1-based).

    Prefer clicking pager links (direct goto to /page/N can fail intermittently).
    """
    n = max(1, int(page_num))
    if n == 1:
        _goto(page, LATEST_URL)
        return

    # Ensure we are on a latest list page first.
    if "/article/latest" not in (page.url or ""):
        _goto(page, LATEST_URL)

    clicked = page.evaluate(
        """(n) => {
          const links = [...document.querySelectorAll('div.paging a, .paging a')];
          const hit = links.find(a => (a.innerText || '').trim() === String(n));
          if (!hit) return {ok: false};
          hit.click();
          return {ok: true, href: hit.href || hit.getAttribute('href')};
        }""",
        n,
    )
    if clicked and clicked.get("ok"):
        try:
            page.wait_for_load_state("domcontentloaded", timeout=30_000)
        except Exception:
            pass
        page.wait_for_timeout(700)
        if f"/page/{n}" in (page.url or "") or (
            n == 1 and page.url.rstrip("/").endswith("/article/latest")
        ):
            return

    # Fallback: absolute URL (with referer context from current page).
    _goto(page, f"{LATEST_URL}/page/{n}")


def scrape_list_items(page: Page) -> list[HbrListItem]:
    raw = page.evaluate(
        """() => {
          const items = [];
          for (const li of document.querySelectorAll('ul.post_list > li')) {
            const a = li.querySelector('a[href*="/article/view/"]');
            if (!a) continue;
            items.push({
              href: a.getAttribute('href') || '',
              abs: a.href,
              subject: (li.querySelector('.subject')?.innerText || a.innerText || '').trim(),
              post_ho: (li.querySelector('.post_ho')?.innerText || '').trim(),
              post_type: (li.querySelector('.post_type')?.innerText || '').trim(),
            });
          }
          return items;
        }"""
    )
    out: list[HbrListItem] = []
    for it in raw or []:
        abs_url = str(it.get("abs") or "")
        if not abs_url and it.get("href"):
            abs_url = urljoin(BASE + "/", str(it["href"]))
        no = article_no_from_url(abs_url)
        if not no:
            continue
        title = str(it.get("subject") or "").strip() or f"article {no}"
        raw_ho = str(it.get("post_ho") or "").strip()
        out.append(
            HbrListItem(
                source_key=no,
                url=abs_url.split("?")[0],
                title=title,
                published_at=parse_post_ho(raw_ho),
                publish_date_raw=raw_ho,
                post_type=str(it.get("post_type") or "").strip(),
                article_no=no,
                atype=atype_from_url(abs_url),
            )
        )
    return out


def fetch_list_page(page: Page, page_num: int) -> list[HbrListItem]:
    open_list_page(page, page_num)
    return scrape_list_items(page)


def capture_article_pdf(page: Page, url: str, dest: Path) -> dict[str, Any]:
    """Open article detail and write ``page.pdf`` to ``dest``."""
    _goto(page, url)
    page.wait_for_timeout(500)
    detail = page.evaluate(
        """() => {
          const body = document.querySelector('#article_body');
          const preview = document.querySelector('section.preview');
          const text = body ? (body.innerText || '') : '';
          return {
            body_len: text.length,
            has_preview: !!preview,
            title: (document.querySelector('.article_header h2, h2')?.innerText
                    || document.title || '').trim(),
          };
        }"""
    )
    if detail.get("has_preview") or int(detail.get("body_len") or 0) < 1500:
        raise RuntimeError(
            f"paywall or short body at {url} "
            f"(len={detail.get('body_len')} preview={detail.get('has_preview')})"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    page.pdf(path=str(dest), format="A4", print_background=True)
    if not dest.is_file() or dest.stat().st_size < 1000:
        raise RuntimeError(f"page.pdf too small: {dest}")
    return {
        "bytes": dest.stat().st_size,
        "body_len": detail.get("body_len"),
        "title": detail.get("title"),
    }


def pdf_page_count(path: Path | str) -> int | None:
    """Return page count via pdfinfo, or None if unavailable."""
    p = Path(path)
    if not p.is_file() or shutil.which("pdfinfo") is None:
        return None
    proc = subprocess.run(
        ["pdfinfo", str(p)],
        capture_output=True,
        check=False,
    )
    text = proc.stdout.decode("utf-8", errors="replace")
    m = re.search(r"^Pages:\s+(\d+)\s*$", text, re.M)
    if not m:
        return None
    try:
        n = int(m.group(1))
    except ValueError:
        return None
    return n if n > 0 else None
