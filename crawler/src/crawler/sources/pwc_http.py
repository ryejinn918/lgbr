"""PwC research-insights HTTP helpers (from adhoc CDP analysis 2026-07-29).

Findings (via ``mode=pwc`` CDP session, not IDE browser):

- List hub: ``https://www.pwc.com/gx/en/research-insights.html``
  (also insights-library.html). Cards: ``a.collection__item-link``.
  Paging control: ``button.collection__load-more`` (page size 8).
- List JSON (no login)::
    ``{COLLECTION_PATH}.filter-dynamic.html?currentPagePath=...&list={}&page={offset}&searchText=&defaultImagePath=...``
  ``page`` is an offset (0, 8, 16, …); response has ``numberHits`` + ``elements``.
- Detail pages are often HTML-only; PDF when present is a normal ``a[href*=".pdf"]``
  (hosts ``www.pwc.com`` / ``assets.pwc.com``). Downloadable via plain HTTP GET.
- Cookie banner / region redirect may appear in browser; HTTP list/PDF calls worked
  without a session cookie from KR.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

SOURCE = "pwc"
BASE = "https://www.pwc.com"
COLLECTION_PATH = (
    "/content/pwc/gx/en/research-insights/jcr:content/root/container/"
    "content-free-container-1/section_906117957/collection_v2_copy"
)
COLLECTION_URL = f"{BASE}{COLLECTION_PATH}.filter-dynamic.html"
DEFAULT_IMAGE_PATH = "/content/dam/pwc/network/collection-fallback-images"
PAGE_SIZE = 8
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_MONTHS = {
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
_PUB_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(\d{1,2}),\s+(\d{4})",
    re.I,
)


@dataclass(frozen=True)
class PwcListItem:
    source_key: str
    title: str
    url: str
    published_at: date | None
    publish_date_raw: str | None
    tags: tuple[str, ...]


def parse_publish_date(raw: str | None) -> date | None:
    if not raw:
        return None
    m = _PUB_RE.search(raw.strip())
    if not m:
        return None
    month = _MONTHS[m.group(1).lower()]
    return date(int(m.group(3)), month, int(m.group(2)))


def source_key_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    if path.endswith(".html"):
        path = path[: -len(".html")]
    key = path.lstrip("/") or url
    return key[:240]


def fetch_list_page(
    page_offset: int = 0,
    *,
    timeout: float = 30.0,
) -> tuple[list[PwcListItem], int]:
    """Return (items, number_hits) for one list page (offset multiples of 8)."""
    if page_offset < 0:
        raise ValueError("page_offset must be >= 0")
    qs = urlencode(
        {
            "currentPagePath": COLLECTION_PATH,
            "list": "{}",
            "page": str(int(page_offset)),
            "searchText": "",
            "defaultImagePath": DEFAULT_IMAGE_PATH,
        }
    )
    url = f"{COLLECTION_URL}?{qs}"
    payload = _get_json(url, timeout=timeout)
    number_hits = int(payload.get("numberHits") or 0)
    elements = payload.get("elements")
    if isinstance(elements, str):
        elements = json.loads(elements)
    if not isinstance(elements, list):
        raise RuntimeError(f"PwC list elements not a list: {type(elements)}")
    items: list[PwcListItem] = []
    for row in elements:
        if not isinstance(row, dict):
            continue
        href = str(row.get("href") or "").strip()
        title = str(row.get("title") or "").strip()
        if not href or not title:
            continue
        pub_raw = str(row.get("publishDate") or "").strip() or None
        tags_raw = row.get("tags") or []
        tags = tuple(str(t) for t in tags_raw) if isinstance(tags_raw, list) else ()
        items.append(
            PwcListItem(
                source_key=source_key_from_url(href),
                title=title,
                url=href,
                published_at=parse_publish_date(pub_raw),
                publish_date_raw=pub_raw,
                tags=tags,
            )
        )
    return items, number_hits


def find_pdf_url(detail_html: str, *, page_url: str) -> str | None:
    """Pick best PDF href from a detail page HTML."""
    hrefs = _PdfHrefParser.extract(detail_html)
    if not hrefs:
        return None
    resolved: list[str] = []
    for href in hrefs:
        abs_url = urljoin(page_url, href)
        if not re.search(r"\.pdf($|\?)", abs_url, re.I):
            continue
        resolved.append(abs_url)
    if not resolved:
        return None

    def score(u: str) -> tuple[int, int]:
        host = urlparse(u).netloc.lower()
        preferred = 0
        if host.endswith("pwc.com") or host.endswith("assets.pwc.com"):
            preferred = 2
        elif "pwc" in host:
            preferred = 1
        return (preferred, -len(u))

    resolved.sort(key=score, reverse=True)
    return resolved[0]


def fetch_detail_pdf_url(url: str, *, timeout: float = 30.0) -> str | None:
    html = _get_text(url, timeout=timeout)
    return find_pdf_url(html, page_url=url)


def download_pdf(url: str, dest_path: Any, *, timeout: float = 120.0) -> int:
    """Download PDF bytes to ``dest_path``. Returns byte length."""
    from pathlib import Path

    path = Path(dest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _get_bytes(url, timeout=timeout)
    if not data.startswith(b"%PDF"):
        raise RuntimeError(f"not a PDF ({url}): magic={data[:8]!r}")
    path.write_bytes(data)
    return len(data)


def _get_json(url: str, *, timeout: float) -> dict[str, Any]:
    raw = _get_text(url, timeout=timeout)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError(f"expected JSON object from {url}")
    return data


def _get_text(url: str, *, timeout: float) -> str:
    return _get_bytes(url, timeout=timeout).decode("utf-8", "ignore")


def _get_bytes(url: str, *, timeout: float) -> bytes:
    req = Request(
        url,
        headers={
            "User-Agent": DEFAULT_UA,
            "Accept": "*/*",
        },
    )
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — trusted PwC hosts
        return resp.read()


class _PdfHrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr = {k.lower(): (v or "") for k, v in attrs}
        href = attr.get("href", "")
        if ".pdf" in href.lower():
            self.hrefs.append(href)

    @classmethod
    def extract(cls, html: str) -> list[str]:
        parser = cls()
        try:
            parser.feed(html)
        except Exception:
            # Fall back to regex if HTML is messy.
            return re.findall(r'href=["\']([^"\']+\.pdf[^"\']*)["\']', html, re.I)
        return parser.hrefs


def months_ago_cutoff(months: int, *, now: datetime | None = None) -> date:
    from calendar import monthrange

    ref = now or datetime.now()
    y, m = ref.year, ref.month - int(months)
    while m <= 0:
        m += 12
        y -= 1
    day = min(ref.day, monthrange(y, m)[1])
    return date(y, m, day)
