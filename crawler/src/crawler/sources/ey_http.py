"""EY US Insights HTTP helpers (api-search list + detail PDF via curl-cffi).

List::
  ``GET …/orchestrators/search/query?i=asengine-en-us&q=…&p=&ps=&s=latest&f=…``
Detail PDF: ``a[href*=".pdf"]`` under ``/content/dam/ey-unified-site/…/documents/``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from curl_cffi import requests

SOURCE = "ey"
BASE = "https://www.ey.com"
DEFAULT_CATALOG = "us"
DEFAULT_QUERY = "report"
PAGE_SIZE = 10
IMPERSONATE = "chrome"
DEFAULT_TIMEOUT = 30.0
SEARCH_INDEX = "asengine-en-us"
SEARCH_QUERY_URL = (
    "https://api-search.ey.com/usepinthi2azf04_Prod/orchestrators/search/query"
)
# Article Type filter values from EY search UI (data-filters Article).
ARTICLE_TYPE_FILTER = (
    "basic,detailed,better-questions,chaptered-article,"
    "q&a-article,video-led,training"
)
HUB_URL = f"{BASE}/en_us/insights"


@dataclass(frozen=True)
class EyCatalog:
    id: str
    label: str
    hub_url: str
    page_size: int = PAGE_SIZE
    query: str = DEFAULT_QUERY
    search_index: str = SEARCH_INDEX


CATALOGS: dict[str, EyCatalog] = {
    "us": EyCatalog(
        id="us",
        label="미국",
        hub_url=HUB_URL,
        page_size=PAGE_SIZE,
        query=DEFAULT_QUERY,
        search_index=SEARCH_INDEX,
    ),
}


def get_catalog(catalog_id: str | None = None) -> EyCatalog:
    key = (catalog_id or DEFAULT_CATALOG).strip().lower() or DEFAULT_CATALOG
    cat = CATALOGS.get(key)
    if cat is None:
        raise ValueError(
            f"unknown EY catalog {catalog_id!r}; "
            f"expected one of: {', '.join(sorted(CATALOGS))}"
        )
    return cat


@dataclass(frozen=True)
class EyListItem:
    source_key: str
    title: str
    url: str
    published_at: date | None
    category: str | None


_ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_PUB_DAY_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(\d{1,2}),\s+(\d{4})",
    re.I,
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


def make_session() -> requests.Session:
    sess = requests.Session(impersonate=IMPERSONATE)
    sess.headers.update(
        {
            "Accept": "application/json,text/html,*/*",
            "Origin": BASE,
            "Referer": HUB_URL,
        }
    )
    return sess


def source_key_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    if path.endswith(".html"):
        path = path[: -len(".html")]
    key = path.lstrip("/") or url
    return key[:240]


def fetch_list_page(
    page: int = 1,
    *,
    catalog: str | EyCatalog | None = None,
    session: requests.Session | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[list[EyListItem], bool]:
    """Return (items, has_more) for one search page (1-based)."""
    if page < 1:
        raise ValueError("page must be >= 1")
    cat = catalog if isinstance(catalog, EyCatalog) else get_catalog(catalog)
    page_size = cat.page_size
    sess = session or make_session()
    params = {
        "i": cat.search_index,
        "q": cat.query,
        "p": str(int(page)),
        "ps": str(page_size),
        "s": "latest",
        "f": ARTICLE_TYPE_FILTER,
    }
    resp = sess.get(
        SEARCH_QUERY_URL,
        params=params,
        headers={
            "Accept": "application/json",
            "Origin": BASE,
            "Referer": f"{BASE}/en_us/search",
        },
        timeout=timeout,
        proxy=None,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"EY list expected JSON object, got {type(payload)}")
    rows = payload.get("search_results")
    if not isinstance(rows, list):
        raise RuntimeError(
            f"EY list search_results not a list: {type(rows)}"
        )
    total = payload.get("results_count")
    try:
        total_n = int(total) if total is not None else None
    except (TypeError, ValueError):
        total_n = None

    items: list[EyListItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = _raw_field(row, "pagetitle") or _raw_field(row, "h1")
        href = _raw_field(row, "url")
        if not title or not href:
            continue
        abs_url = urljoin(BASE, href)
        path = urlparse(abs_url).path.lower()
        if not _keep_list_url(path):
            continue
        pub = _parse_api_date(
            _raw_field(row, "dateuser") or _raw_field(row, "firstpublishdate")
        )
        topic = _raw_field(row, "topiclabel")
        if isinstance(row.get("topiclabel"), list) and row["topiclabel"]:
            first = row["topiclabel"][0]
            topic = str(first) if first is not None else topic
        items.append(
            EyListItem(
                source_key=source_key_from_url(abs_url),
                title=title.strip(),
                url=abs_url,
                published_at=pub,
                category=topic,
            )
        )

    if total_n is not None:
        has_more = page * page_size < total_n
    else:
        has_more = len(rows) >= page_size
    return items, has_more


def find_pdf_url(detail_html: str, *, page_url: str) -> str | None:
    rows = _PdfHrefParser.extract(detail_html)
    if not rows:
        for href in re.findall(
            r'href=["\']([^"\']+\.pdf[^"\']*)["\']', detail_html, re.I
        ):
            rows.append((href, "", ""))
    resolved: list[tuple[str, str, str]] = []
    for href, aria, text in rows:
        abs_url = urljoin(page_url, href.split("#", 1)[0])
        if not re.search(r"\.pdf($|\?)", abs_url, re.I):
            continue
        resolved.append((abs_url, (aria or "").lower(), (text or "").lower()))
    if not resolved:
        return None

    def score(row: tuple[str, str, str]) -> tuple[int, int, int]:
        u, aria, text = row
        path = urlparse(u).path.lower()
        preferred = 0
        if "/content/dam/ey-unified-site/" in path and "/documents/" in path:
            preferred += 5
        elif "/content/dam/ey-unified-site/" in path:
            preferred += 3
        elif "/content/dam/" in path:
            preferred += 1
        if "transcript" in path:
            preferred -= 5
        if "download" in aria or "download" in text or "pdf" in text:
            preferred += 2
        return (preferred, -len(path), -len(u))

    resolved.sort(key=score, reverse=True)
    return resolved[0][0]


def parse_publish_date_from_html(html: str) -> date | None:
    m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
    if m:
        d = _parse_api_date(m.group(1))
        if d:
            return d
    m = _PUB_DAY_RE.search(html)
    if m:
        month = _MONTHS[m.group(1).lower()]
        return date(int(m.group(3)), month, int(m.group(2)))
    return None


def fetch_detail_meta(
    url: str,
    *,
    session: requests.Session | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[str | None, date | None]:
    sess = session or make_session()
    resp = sess.get(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Referer": HUB_URL,
        },
        timeout=timeout,
        proxy=None,
    )
    resp.raise_for_status()
    html = resp.text
    return find_pdf_url(html, page_url=url), parse_publish_date_from_html(html)


def download_pdf(
    url: str,
    dest_path: Any,
    *,
    session: requests.Session | None = None,
    timeout: float = 120.0,
) -> int:
    path = Path(dest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sess = session or make_session()
    resp = sess.get(
        url,
        headers={
            "Accept": "application/pdf,*/*",
            "Referer": HUB_URL,
        },
        timeout=timeout,
        proxy=None,
    )
    resp.raise_for_status()
    data = resp.content
    if not data.startswith(b"%PDF"):
        raise RuntimeError(f"not a PDF ({url}): magic={data[:8]!r}")
    path.write_bytes(data)
    return len(data)


def pdf_page_count(path: Path | str) -> int | None:
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


def months_ago_cutoff(months: int, *, now: datetime | None = None) -> date:
    ref = now or datetime.now()
    y, m = ref.year, ref.month - int(months)
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def _keep_list_url(path: str) -> bool:
    if "/people/" in path:
        return False
    if "/webcast" in path or "/podcast" in path:
        return False
    if "/careers/" in path:
        return False
    # Prefer insight articles; drop service/industry landing pages.
    return "/insights/" in path


def _raw_field(row: dict[str, Any], name: str) -> str | None:
    raw = row.get(name)
    if raw is None:
        return None
    if isinstance(raw, dict):
        val = raw.get("raw")
        if val is None:
            return None
        s = str(val).strip()
        return s or None
    if isinstance(raw, list):
        return None
    s = str(raw).strip()
    return s or None


def _parse_api_date(raw: str | None) -> date | None:
    if not raw:
        return None
    m = _ISO_DATE_RE.search(raw.strip())
    if not m:
        return None
    try:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    except ValueError:
        return None
    # EY uses placeholder far-future dates on evergreen service pages.
    if y >= 9000:
        return None
    try:
        return date(y, mo, d)
    except ValueError:
        return None


class _PdfHrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[tuple[str, str, str]] = []
        self._in_a = False
        self._href = ""
        self._aria = ""
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr = {k.lower(): (v or "") for k, v in attrs}
        href = attr.get("href", "")
        if ".pdf" not in href.lower():
            return
        self._in_a = True
        self._href = href
        self._aria = attr.get("aria-label", "")
        self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_a:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._in_a:
            return
        self.rows.append(
            (self._href, self._aria, "".join(self._text_parts).strip())
        )
        self._in_a = False

    @classmethod
    def extract(cls, html: str) -> list[tuple[str, str, str]]:
        parser = cls()
        try:
            parser.feed(html)
        except Exception:
            return []
        return parser.rows
