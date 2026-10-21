"""PwC Insights HTTP helpers (catalogs: Korea / Global).

List data is returned either by the legacy JSON endpoint or embedded in the
current ``collection_v2.dynamic.html`` component. Detail PDF:
``a[href*=".pdf"]``.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

from curl_cffi import requests

from crawler.sources.browser_http import (
    DEFAULT_TIMEOUT,
    get_bytes,
    get_json,
    get_text,
    make_session as _make_session,
)

SOURCE = "pwc"
BASE = "https://www.pwc.com"
DEFAULT_IMAGE_PATH = "/content/dam/pwc/network/collection-fallback-images"
DEFAULT_CATALOG = "kr"


@dataclass(frozen=True)
class PwcCatalog:
    id: str
    label: str
    hub_url: str
    collection_path: str
    page_size: int

    @property
    def collection_url(self) -> str:
        return f"{BASE}{self.collection_path}.filter-dynamic.html"

    @property
    def dynamic_url(self) -> str:
        path = self.collection_path.replace("/jcr:content/", "/_jcr_content/")
        return f"{BASE}{path}.dynamic.html"


CATALOGS: dict[str, PwcCatalog] = {
    "kr": PwcCatalog(
        id="kr",
        label="한국 (삼일)",
        hub_url="https://www.pwc.com/kr/ko/insights.html",
        collection_path=(
            "/content/pwc/kr/ko/insights/jcr:content/root/container/"
            "content-free-container-1/section_916288947_co/collection_v2"
        ),
        page_size=4,
    ),
    "gx": PwcCatalog(
        id="gx",
        label="국제",
        hub_url="https://www.pwc.com/gx/en/research-insights.html",
        collection_path=(
            "/content/pwc/gx/en/research-insights/jcr:content/root/container/"
            "content-free-container-1/section_906117957/collection_v2_copy"
        ),
        page_size=8,
    ),
}

# Back-compat aliases used by older call sites.
COLLECTION_PATH = CATALOGS[DEFAULT_CATALOG].collection_path
COLLECTION_URL = CATALOGS[DEFAULT_CATALOG].collection_url
PAGE_SIZE = CATALOGS[DEFAULT_CATALOG].page_size


def get_catalog(catalog_id: str | None = None) -> PwcCatalog:
    key = (catalog_id or DEFAULT_CATALOG).strip().lower() or DEFAULT_CATALOG
    cat = CATALOGS.get(key)
    if cat is None:
        raise ValueError(
            f"unknown PwC catalog {catalog_id!r}; "
            f"expected one of: {', '.join(sorted(CATALOGS))}"
        )
    return cat


def list_catalogs() -> list[PwcCatalog]:
    return [CATALOGS[k] for k in ("kr", "gx") if k in CATALOGS]


def make_session(catalog: str | PwcCatalog | None = None) -> requests.Session:
    cat = catalog if isinstance(catalog, PwcCatalog) else get_catalog(catalog)
    return _make_session(referer=cat.hub_url, origin=BASE, accept="*/*")


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
_PUB_DAY_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(\d{1,2}),\s+(\d{4})",
    re.I,
)
_PUB_MONTH_RE = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(\d{4})$",
    re.I,
)
_PUB_DMY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$")


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
    text = raw.strip()
    m = _PUB_DAY_RE.search(text)
    if m:
        month = _MONTHS[m.group(1).lower()]
        return date(int(m.group(3)), month, int(m.group(2)))
    m = _PUB_MONTH_RE.match(text)
    if m:
        month = _MONTHS[m.group(1).lower()]
        return date(int(m.group(2)), month, 1)
    m = _PUB_DMY_RE.match(text)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def source_key_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    if path.endswith(".html"):
        path = path[: -len(".html")]
    key = path.lstrip("/") or url
    return key[:240]


def fetch_list_page(
    page_offset: int = 0,
    *,
    catalog: str | PwcCatalog | None = None,
    session: requests.Session | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[list[PwcListItem], int]:
    """Return (items, number_hits) for one list page."""
    if page_offset < 0:
        raise ValueError("page_offset must be >= 0")
    cat = catalog if isinstance(catalog, PwcCatalog) else get_catalog(catalog)
    qs = urlencode(
        {
            "currentPagePath": cat.collection_path,
            "list": "{}",
            "page": str(int(page_offset)),
            "searchText": "",
            "defaultImagePath": DEFAULT_IMAGE_PATH,
        }
    )
    url = f"{cat.collection_url}?{qs}"
    sess = session or make_session(cat)
    try:
        payload = get_json(
            sess,
            url,
            headers={
                "Accept": "application/json,*/*",
                "Referer": cat.hub_url,
            },
            timeout=timeout,
        )
    except (json.JSONDecodeError, ValueError):
        component_html = get_text(
            sess,
            cat.dynamic_url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Referer": cat.hub_url,
            },
            timeout=timeout,
        )
        payload = _parse_dynamic_payload(component_html)
        if page_offset > 0:
            payload["elements"] = []
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object from {url}")
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


_LOAD_FACETED_PAYLOAD_RE = re.compile(
    r'angular\.loadFacetedNavigation\(\s*'
    r'(?:"(?:\\.|[^"\\])*"\s*,\s*){5}'
    r'"((?:\\.|[^"\\])*)"',
    re.S,
)


def _parse_dynamic_payload(html: str) -> dict[str, Any]:
    match = _LOAD_FACETED_PAYLOAD_RE.search(html)
    if match is None:
        raise RuntimeError("PwC dynamic collection payload not found")
    raw = re.sub(
        r"\\x([0-9a-fA-F]{2})",
        lambda found: rf"\u00{found.group(1)}",
        match.group(1),
    )
    payload_text = json.loads(f'"{raw}"')
    payload = json.loads(payload_text)
    if not isinstance(payload, dict):
        raise RuntimeError("PwC dynamic collection payload is not an object")
    return payload


def is_pdf_url(url: str) -> bool:
    """True when the URL itself is a PDF (list item may link directly)."""
    return bool(re.search(r"\.pdf($|\?)", url or "", re.I))


def find_pdf_url(detail_html: str, *, page_url: str) -> str | None:
    """Pick best PDF href from a detail page HTML."""
    hrefs = _PdfHrefParser.extract(detail_html)
    if not hrefs:
        return None
    resolved: list[str] = []
    for href in hrefs:
        abs_url = urljoin(page_url, href)
        if not is_pdf_url(abs_url):
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


def fetch_detail_pdf_url(
    url: str,
    *,
    catalog: str | PwcCatalog | None = None,
    session: requests.Session | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str | None:
    cat = catalog if isinstance(catalog, PwcCatalog) else get_catalog(catalog)
    sess = session or make_session(cat)
    html = get_text(
        sess,
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Referer": cat.hub_url,
        },
        timeout=timeout,
    )
    return find_pdf_url(html, page_url=url)


def download_pdf(
    url: str,
    dest_path: Any,
    *,
    catalog: str | PwcCatalog | None = None,
    session: requests.Session | None = None,
    timeout: float = 120.0,
) -> int:
    """Download PDF bytes to ``dest_path``. Returns byte length."""
    path = Path(dest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cat = catalog if isinstance(catalog, PwcCatalog) else get_catalog(catalog)
    sess = session or make_session(cat)
    data = get_bytes(
        sess,
        url,
        headers={
            "Accept": "application/pdf,*/*",
            "Referer": cat.hub_url,
        },
        timeout=timeout,
    )
    if not data.startswith(b"%PDF"):
        raise RuntimeError(f"not a PDF ({url}): magic={data[:8]!r}")
    path.write_bytes(data)
    return len(data)


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
    """Earliest publish date to keep (inclusive).

    Uses the first day of the cutoff month so month-only dates like
    ``July 2026`` (stored as the 1st) are not dropped mid-month.
    """
    ref = now or datetime.now()
    y, m = ref.year, ref.month - int(months)
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)
