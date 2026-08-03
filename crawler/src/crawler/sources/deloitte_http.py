"""Deloitte US Insights HTTP helpers (OpenSearch template list + detail PDF).

List::
  ``POST …/modern-prod-english/_search/template``
  with header ``d-target: elastic`` and template id
  ``modern-insights-internal-search-template``.
Detail PDF: ``a[href*=".pdf"]`` under ``/content/dam/insights/``.
"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

from curl_cffi import requests

from crawler.sources.browser_http import (
    DEFAULT_TIMEOUT,
    get_bytes,
    get_text,
    make_session as _make_session,
    post,
)

SOURCE = "deloitte"
BASE = "https://www.deloitte.com"
DEFAULT_CATALOG = "us"
DEFAULT_PROFILE = "report"
PAGE_SIZE = 10
TEMPLATE_ID = "modern-insights-internal-search-template"
TEMPLATE_URL = f"{BASE}/modern-prod-english/_search/template"
PAGE_TYPES = ("insights-article",)
HUB_URL = f"{BASE}/us/en/insights.html"
SEARCH_RESULTS_URL = f"{BASE}/us/en/insights/searchresults.html"


@dataclass(frozen=True)
class DeloitteCatalog:
    id: str
    label: str
    hub_url: str
    page_size: int = PAGE_SIZE


CATALOGS: dict[str, DeloitteCatalog] = {
    "us": DeloitteCatalog(
        id="us",
        label="미국",
        hub_url=HUB_URL,
        page_size=PAGE_SIZE,
    ),
}


@dataclass(frozen=True)
class DeloitteProfile:
    id: str
    label: str
    queries: tuple[str, ...]
    period_months: int = 3


# FnGuide theme ids + report; English queries for Insights US index.
PROFILES: dict[str, DeloitteProfile] = {
    "report": DeloitteProfile(
        id="report",
        label="Report",
        queries=("report",),
    ),
    "ai": DeloitteProfile(
        id="ai",
        label="AI",
        queries=("AI", "AI semiconductor", "generative AI", "LLM"),
    ),
    "datacenter": DeloitteProfile(
        id="datacenter",
        label="데이터센터",
        queries=("data center", "AIDC", "power", "cooling"),
    ),
    "physical_ai": DeloitteProfile(
        id="physical_ai",
        label="피지컬 AI",
        queries=(
            "Physical AI",
            "humanoid",
            "robotics",
            "robot",
            "on-device",
        ),
    ),
    "appliance": DeloitteProfile(
        id="appliance",
        label="가전",
        queries=("appliance", "consumer electronics", "HVAC", "TV"),
    ),
    "display": DeloitteProfile(
        id="display",
        label="디스플레이",
        queries=("display", "OLED", "panel"),
    ),
    "automotive": DeloitteProfile(
        id="automotive",
        label="자동차",
        queries=("automotive", "EV", "mobility", "battery", "SDV"),
    ),
    "petrochemical": DeloitteProfile(
        id="petrochemical",
        label="석유화학",
        queries=("chemicals", "petrochemical", "chemical"),
    ),
}

PROFILE_IDS = frozenset(PROFILES)


def get_catalog(catalog_id: str | None = None) -> DeloitteCatalog:
    key = (catalog_id or DEFAULT_CATALOG).strip().lower() or DEFAULT_CATALOG
    cat = CATALOGS.get(key)
    if cat is None:
        raise ValueError(
            f"unknown Deloitte catalog {catalog_id!r}; "
            f"expected one of: {', '.join(sorted(CATALOGS))}"
        )
    return cat


def get_profile(profile_id: str | None = None) -> DeloitteProfile:
    key = (profile_id or DEFAULT_PROFILE).strip().lower() or DEFAULT_PROFILE
    prof = PROFILES.get(key)
    if prof is None:
        raise ValueError(
            f"unknown Deloitte profile {profile_id!r}; "
            f"expected one of: {', '.join(sorted(PROFILES))}"
        )
    return prof


@dataclass(frozen=True)
class DeloitteListItem:
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
    return _make_session(
        referer=HUB_URL,
        origin=BASE,
        accept="application/json, text/plain, */*",
    )


def source_key_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    if path.endswith(".html"):
        path = path[: -len(".html")]
    key = path.lstrip("/") or url
    return key[:240]


def fetch_list_page(
    page: int = 1,
    *,
    catalog: str | DeloitteCatalog | None = None,
    query: str,
    session: requests.Session | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[list[DeloitteListItem], bool]:
    """Return (items, has_more) for one search page (1-based)."""
    if page < 1:
        raise ValueError("page must be >= 1")
    q = (query or "").strip()
    if not q:
        raise ValueError("query must be non-empty")
    cat = (
        catalog
        if isinstance(catalog, DeloitteCatalog)
        else get_catalog(catalog)
    )
    page_size = cat.page_size
    sess = session or make_session()
    offset = (page - 1) * page_size
    body = {
        "id": TEMPLATE_ID,
        "params": {
            "query-string": q,
            "from": offset,
            "size": page_size,
            "site-name": cat.id,
            "language": "en",
            "page-type": list(PAGE_TYPES),
        },
    }
    payload = post(
        sess,
        TEMPLATE_URL,
        json=body,
        headers={
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": BASE,
            "Referer": f"{SEARCH_RESULTS_URL}?qr={q}",
            "d-target": "elastic",
        },
        timeout=timeout,
    )
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"Deloitte list expected JSON object, got {type(payload)}"
        )
    hits_wrap = payload.get("hits")
    if not isinstance(hits_wrap, dict):
        raise RuntimeError(
            f"Deloitte list hits not an object: {type(hits_wrap)}"
        )
    rows = hits_wrap.get("hits")
    if not isinstance(rows, list):
        raise RuntimeError(f"Deloitte list hits.hits not a list: {type(rows)}")
    total_raw = hits_wrap.get("total")
    total_n: int | None
    if isinstance(total_raw, dict):
        try:
            total_n = int(total_raw.get("value"))
        except (TypeError, ValueError):
            total_n = None
    else:
        try:
            total_n = int(total_raw) if total_raw is not None else None
        except (TypeError, ValueError):
            total_n = None

    items: list[DeloitteListItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        src = row.get("_source")
        if not isinstance(src, dict):
            continue
        title = _str_field(src.get("title"))
        href = _str_field(src.get("url"))
        if not title or not href:
            continue
        abs_url = urljoin(BASE, href)
        path = urlparse(abs_url).path.lower()
        if not _keep_list_url(path):
            continue
        pub = _parse_api_date(_str_field(src.get("date-published")))
        page_type = _str_field(src.get("page-type"))
        items.append(
            DeloitteListItem(
                source_key=source_key_from_url(abs_url),
                title=title.strip(),
                url=abs_url,
                published_at=pub,
                category=page_type,
            )
        )

    if total_n is not None:
        has_more = offset + page_size < total_n
    else:
        has_more = len(rows) >= page_size
    return items, has_more


def _is_deloitte_host(host: str) -> bool:
    h = (host or "").lower().split(":")[0]
    return h == "deloitte.com" or h.endswith(".deloitte.com")


def find_pdf_url(detail_html: str, *, page_url: str) -> str | None:
    """Pick a Deloitte-hosted PDF only (ignore cited third-party .pdf links)."""
    rows = _PdfHrefParser.extract(detail_html)
    if not rows:
        for href in re.findall(
            r'href=["\']([^"\']+\.pdf[^"\']*)["\']', detail_html, re.I
        ):
            rows.append((href, "", ""))
    resolved: list[tuple[str, str, str]] = []
    for href, aria, text in rows:
        cleaned = html.unescape(href.split("#", 1)[0])
        abs_url = urljoin(page_url, cleaned)
        abs_url = _strip_fragment(abs_url)
        if not re.search(r"\.pdf($|\?)", abs_url, re.I):
            continue
        if not _is_deloitte_host(urlparse(abs_url).netloc):
            continue
        resolved.append((abs_url, (aria or "").lower(), (text or "").lower()))
    if not resolved:
        return None

    def score(row: tuple[str, str, str]) -> tuple[int, int, int]:
        u, aria, text = row
        path = urlparse(u).path.lower()
        preferred = 0
        if "/content/dam/insights/" in path:
            preferred += 5
        elif "/content/dam/" in path:
            preferred += 2
        if "transcript" in path:
            preferred -= 5
        if "download" in aria or "download" in text or "pdf" in text:
            preferred += 2
        return (preferred, -len(path), -len(u))

    resolved.sort(key=score, reverse=True)
    return resolved[0][0]


def parse_publish_date_from_html(html_text: str) -> date | None:
    m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html_text)
    if m:
        d = _parse_api_date(m.group(1))
        if d:
            return d
    m = _PUB_DAY_RE.search(html_text)
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
    html_text = get_text(
        sess,
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Referer": HUB_URL,
        },
        timeout=timeout,
    )
    return (
        find_pdf_url(html_text, page_url=url),
        parse_publish_date_from_html(html_text),
    )


def download_pdf(
    url: str,
    dest_path: Any,
    *,
    session: requests.Session | None = None,
    timeout: float = 120.0,
) -> int:
    if not _is_deloitte_host(urlparse(url).netloc):
        raise RuntimeError(f"refusing non-Deloitte PDF host: {url}")
    path = Path(dest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sess = session or make_session()
    data = get_bytes(
        sess,
        url,
        headers={
            "Accept": "application/pdf,*/*",
            "Referer": HUB_URL,
        },
        timeout=timeout,
    )
    if not data.startswith(b"%PDF"):
        raise RuntimeError(f"not a PDF ({url}): magic={data[:8]!r}")
    if len(data) < 20_000:
        raise RuntimeError(f"PDF too small ({url}): bytes={len(data)}")
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
    if "/careers/" in path:
        return False
    return "/insights/" in path


def _str_field(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        if not raw:
            return None
        raw = raw[0]
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
    if y >= 9000:
        return None
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _strip_fragment(url: str) -> str:
    parts = urlparse(url)
    if not parts.fragment:
        return url
    return urlunparse(parts._replace(fragment=""))


class _PdfHrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[tuple[str, str, str]] = []
        self._in_a = False
        self._href = ""
        self._aria = ""
        self._text_parts: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
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
    def extract(cls, html_text: str) -> list[tuple[str, str, str]]:
        parser = cls()
        try:
            parser.feed(html_text)
        except Exception:
            return []
        return parser.rows
