"""Accenture US Insights HTTP helpers (list via filtercard API + detail PDF).

List::
  ``POST /api/accenture/tilegrid/filtercard`` (multipart) on insights-index.
Detail PDF: ``a[href*=".pdf"]`` under ``/content/dam/accenture/...``.
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
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

SOURCE = "accenture"
BASE = "https://www.accenture.com"
FILTERCARD_URL = f"{BASE}/api/accenture/tilegrid/filtercard"
DEFAULT_CATALOG = "us"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_TAGS = ("universal:filter-types/research-report",)
PAGE_SIZE = 12  # client requests size=page_size+1 to detect has_more


@dataclass(frozen=True)
class AccentureCatalog:
    id: str
    label: str
    hub_url: str
    index_url: str
    resource_path: str
    geo_tag: str
    locale: str
    page_size: int = PAGE_SIZE


CATALOGS: dict[str, AccentureCatalog] = {
    "us": AccentureCatalog(
        id="us",
        label="미국",
        hub_url="https://www.accenture.com/us-en/insights",
        index_url="https://www.accenture.com/us-en/insights-index",
        resource_path=(
            "/content/acom/us-en/insights-index/jcr:content/"
            "root/container_main/filtercardv2"
        ),
        geo_tag="universal:country-codes/core-multi-market/us-en",
        locale="us-en",
        page_size=PAGE_SIZE,
    ),
}


def get_catalog(catalog_id: str | None = None) -> AccentureCatalog:
    key = (catalog_id or DEFAULT_CATALOG).strip().lower() or DEFAULT_CATALOG
    cat = CATALOGS.get(key)
    if cat is None:
        raise ValueError(
            f"unknown Accenture catalog {catalog_id!r}; "
            f"expected one of: {', '.join(sorted(CATALOGS))}"
        )
    return cat


@dataclass(frozen=True)
class AccentureListItem:
    source_key: str
    title: str
    url: str
    content_type: str | None
    cf_id: str | None


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


def source_key_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    if path.endswith(".html"):
        path = path[: -len(".html")]
    key = path.lstrip("/") or url
    return key[:240]


def fetch_list_page(
    offset: int = 0,
    *,
    catalog: str | AccentureCatalog | None = None,
    tags: tuple[str, ...] = DEFAULT_TAGS,
    timeout: float = 30.0,
) -> tuple[list[AccentureListItem], bool]:
    """Return (items, has_more) for one list page."""
    if offset < 0:
        raise ValueError("offset must be >= 0")
    cat = catalog if isinstance(catalog, AccentureCatalog) else get_catalog(catalog)
    page_size = cat.page_size
    # Request one extra row so the client can detect more pages.
    req_size = page_size + 1
    fields = {
        "resourcePath": cat.resource_path,
        "geoTag": cat.geo_tag,
        "locale": cat.locale,
        "disableLinkConversion": "false",
        "size": str(req_size),
        "offset": str(int(offset)),
        "orderBy": "jcr:content/metadata/date",
        "sortOrder": "desc",
    }
    if tags:
        fields["tags"] = ",".join(tags)
    payload = _post_multipart(FILTERCARD_URL, fields, timeout=timeout)
    if payload.get("error"):
        raise RuntimeError(f"Accenture list error: {payload.get('error')}")
    rows = payload.get("contentFragmentItems")
    if not isinstance(rows, list):
        raise RuntimeError(
            f"Accenture list items not a list: {type(rows)}"
        )
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    items: list[AccentureListItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cta = str(row.get("ctaLink") or "").strip()
        title = str(row.get("title") or "").strip()
        if not cta or not title:
            continue
        url = urljoin(BASE, cta)
        items.append(
            AccentureListItem(
                source_key=source_key_from_url(url),
                title=title,
                url=url,
                content_type=str(row.get("contentType") or "") or None,
                cf_id=str(row.get("cfId") or "") or None,
            )
        )
    return items, has_more


def find_pdf_url(detail_html: str, *, page_url: str) -> str | None:
    """Pick best report PDF href from a detail page HTML."""
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
        if "/content/dam/accenture/final/accenture-com/document" in path:
            preferred += 4
        elif "/content/dam/accenture/" in path:
            preferred += 2
        if "transcript" in path or "a-com-no-follow" in path:
            preferred -= 5
        if "download" in aria or "download" in text:
            preferred += 2
        return (preferred, -len(path), -len(u))

    resolved.sort(key=score, reverse=True)
    return resolved[0][0]


def parse_publish_date_from_html(html: str) -> date | None:
    """Prefer hero publish date / contentDate; fall back to JSON-LD."""
    m = re.search(
        r'class="[^"]*rad-article-hero__publish-date[^"]*"[^>]*>\s*([^<]+)',
        html,
        re.I,
    )
    if m:
        d = _parse_english_date(m.group(1))
        if d:
            return d
    m = re.search(
        r'"contentDate"\s*:\s*"([^"]+)"',
        html,
    )
    if m:
        d = _parse_iso_date(m.group(1))
        if d:
            return d
    m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
    if m:
        return _parse_iso_date(m.group(1))
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


def _post_multipart(
    url: str, fields: dict[str, str], *, timeout: float
) -> dict[str, Any]:
    boundary = "----lgbrAccentureBoundary7MA4YWxkTrZu0gW"
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
        )
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    body = b"".join(chunks)
    req = Request(
        url,
        data=body,
        method="POST",
        headers={
            "User-Agent": DEFAULT_UA,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "CSRF-Token": "",
            "Origin": BASE,
            "Referer": f"{BASE}/us-en/insights-index",
        },
    )
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310
        raw = resp.read().decode("utf-8", "ignore")
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
