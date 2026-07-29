"""KPMG US Insights HTTP helpers (Cludo list + detail PDF).

List::
  ``GET …/insights-and-resources/_jcr_content.cludosearch.json``
Detail PDF: ``a[href*=".pdf"]`` under ``/kpmg-us/content/dam/kpmg/pdf/``.
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
from urllib.request import Request, urlopen

SOURCE = "kpmg"
BASE = "https://kpmg.com"
DEFAULT_CATALOG = "us"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_QUERY = "report"
PAGE_SIZE = 12
CLUDO_PATH = (
    "/kpmg-us/content/kpmg/us/en/insights-and-resources/"
    "_jcr_content.cludosearch.json"
)


@dataclass(frozen=True)
class KpmgCatalog:
    id: str
    label: str
    hub_url: str
    list_url: str
    page_size: int = PAGE_SIZE
    query: str = DEFAULT_QUERY


CATALOGS: dict[str, KpmgCatalog] = {
    "us": KpmgCatalog(
        id="us",
        label="미국",
        hub_url="https://kpmg.com/us/en/insights-and-resources.html",
        list_url=urljoin(BASE, CLUDO_PATH),
        page_size=PAGE_SIZE,
        query=DEFAULT_QUERY,
    ),
}


def get_catalog(catalog_id: str | None = None) -> KpmgCatalog:
    key = (catalog_id or DEFAULT_CATALOG).strip().lower() or DEFAULT_CATALOG
    cat = CATALOGS.get(key)
    if cat is None:
        raise ValueError(
            f"unknown KPMG catalog {catalog_id!r}; "
            f"expected one of: {', '.join(sorted(CATALOGS))}"
        )
    return cat


@dataclass(frozen=True)
class KpmgListItem:
    source_key: str
    title: str
    url: str
    published_at: date | None
    category: str | None


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
_ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_US_SLASH_RE = re.compile(
    r"(\d{1,2})/(\d{1,2})/(\d{4})"
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
    catalog: str | KpmgCatalog | None = None,
    timeout: float = 30.0,
) -> tuple[list[KpmgListItem], bool]:
    """Return (items, has_more) for one Cludo search page (1-based)."""
    if page < 1:
        raise ValueError("page must be >= 1")
    cat = catalog if isinstance(catalog, KpmgCatalog) else get_catalog(catalog)
    page_size = cat.page_size
    params = {
        "type": "search",
        "query": cat.query,
        "page": str(int(page)),
        "perPage": str(page_size),
        "contentType": "Insight",
    }
    url = f"{cat.list_url}?{urlencode(params)}"
    payload = _get_json(url, timeout=timeout)
    rows = payload.get("TypedDocuments")
    if not isinstance(rows, list):
        raise RuntimeError(
            f"KPMG list TypedDocuments not a list: {type(rows)}"
        )
    total = payload.get("TotalDocument")
    try:
        total_n = int(total) if total is not None else None
    except (TypeError, ValueError):
        total_n = None

    items: list[KpmgListItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        fields = row.get("Fields")
        if not isinstance(fields, dict):
            continue
        title = _field_value(fields, "Title") or _field_value(
            fields, "CardTitle"
        )
        href = _field_value(fields, "Url")
        if not title or not href:
            continue
        abs_url = urljoin(BASE, href)
        if "/webcasts/" in urlparse(abs_url).path.lower():
            continue
        pub = _parse_publish_date(
            _field_value(fields, "PublishDate")
            or _field_value(fields, "DisplayDate")
            or _field_value(fields, "SortDate")
        )
        items.append(
            KpmgListItem(
                source_key=source_key_from_url(abs_url),
                title=title.strip(),
                url=abs_url,
                published_at=pub,
                category=_field_value(fields, "Category"),
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
        if "/content/dam/kpmg/pdf/" in path:
            preferred += 4
        elif "/content/dam/kpmg/" in path:
            preferred += 2
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
        d = _parse_iso_date(m.group(1)) or _parse_publish_date(m.group(1))
        if d:
            return d
    m = re.search(
        r'class="[^"]*(?:publish|article)[^"]*date[^"]*"[^>]*>\s*([^<]+)',
        html,
        re.I,
    )
    if m:
        d = _parse_publish_date(m.group(1))
        if d:
            return d
    return None


def fetch_detail_meta(
    url: str, *, timeout: float = 30.0
) -> tuple[str | None, date | None]:
    html = _get_text(url, timeout=timeout)
    return find_pdf_url(html, page_url=url), parse_publish_date_from_html(html)


def download_pdf(url: str, dest_path: Any, *, timeout: float = 120.0) -> int:
    path = Path(dest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _get_bytes(url, timeout=timeout)
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


def _field_value(fields: dict[str, Any], name: str) -> str | None:
    raw = fields.get(name)
    if not isinstance(raw, dict):
        return None
    val = raw.get("Value")
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def _parse_publish_date(raw: str | None) -> date | None:
    if not raw:
        return None
    text = raw.strip()
    d = _parse_english_date(text)
    if d:
        return d
    d = _parse_iso_date(text)
    if d:
        return d
    m = _US_SLASH_RE.search(text)
    if m:
        try:
            # M/D/Y (Cludo SortDate)
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    return None


def _parse_english_date(raw: str) -> date | None:
    m = _PUB_DAY_RE.search(raw.strip())
    if not m:
        return None
    month = _MONTHS[m.group(1).lower()]
    return date(int(m.group(3)), month, int(m.group(2)))


def _parse_iso_date(raw: str) -> date | None:
    m = _ISO_DATE_RE.search(raw.strip())
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _get_json(url: str, *, timeout: float) -> dict[str, Any]:
    raw = _get_bytes(url, timeout=timeout).decode("utf-8", "ignore")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError(f"expected JSON object from {url}")
    if data.get("status") == "500" or data.get("error"):
        raise RuntimeError(
            f"KPMG list error: {data.get('error') or data.get('status')}"
        )
    return data


def _get_text(url: str, *, timeout: float) -> str:
    return _get_bytes(url, timeout=timeout).decode("utf-8", "ignore")


def _get_bytes(url: str, *, timeout: float) -> bytes:
    req = Request(
        url,
        headers={
            "User-Agent": DEFAULT_UA,
            "Accept": "*/*",
            "Referer": f"{BASE}/us/en/insights-and-resources.html",
        },
    )
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


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
