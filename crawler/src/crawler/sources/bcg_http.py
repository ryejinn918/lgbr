"""BCG Insights HTTP helpers (allowlisted list HTML + detail PDF).

Profiles / URL guards live in ``bcg_browser`` (single source). Search jobs use
this module; adhoc/probe keep Patchright.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from curl_cffi import requests

from crawler.sources.bcg_browser import (
    BASE,
    HUB_URL,
    LIST_URL,
    BcgBlockedError,
    BcgCaptureError,
    BcgListItem,
    BcgProfile,
    DEFAULT_PROFILE,
    PROFILE_IDS,
    PROFILES,
    SOURCE,
    get_profile,
    is_allowlisted_list_url,
    is_publication_article_url,
    is_publications_hub,
    months_ago_cutoff,
    normalize_list_url,
    parse_bcg_date,
    slug_from_url,
    source_key_from_url,
)
from crawler.sources.browser_http import (
    DEFAULT_TIMEOUT,
    get_bytes,
    get_text,
    make_session as _make_session,
)

_DENIED_RE = re.compile(
    r"access\s*denied|errors\.edgesuite|reference\s*#",
    re.I,
)
_HREF_PUB_RE = re.compile(
    r"""href=["']([^"']*publications/\d{4}/[^"'#?]+)""",
    re.I,
)
_DATE_NEAR_RE = re.compile(
    r"\b(?:"
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?"
    r")\s+\d{1,2},?\s+\d{4}\b",
    re.I,
)
_TITLE_RE = re.compile(
    r"<a[^>]+href=[\"']([^\"']*publications/\d{4}/[^\"'#?]+)[\"'][^>]*>"
    r"\s*([^<]{12,300})\s*</a>",
    re.I | re.S,
)


def make_session() -> requests.Session:
    return _make_session(
        referer=HUB_URL,
        origin=BASE,
        accept="text/html,application/xhtml+xml,application/json,*/*",
    )


def _assert_not_denied(text: str, *, where: str) -> None:
    if _DENIED_RE.search(text or ""):
        raise BcgBlockedError(f"access denied at {where}")


def parse_list_html(html: str, *, list_url: str) -> list[BcgListItem]:
    """Extract publication cards from a list-surface HTML body."""
    body = html or ""
    _assert_not_denied(body[:4000], where=list_url)
    items: list[BcgListItem] = []
    seen: set[str] = set()

    # Collect titled anchors first so date windows stay between neighbors.
    titled: list[tuple[re.Match[str], str, str, str]] = []
    for m in _TITLE_RE.finditer(body):
        href = urljoin(list_url, m.group(1).split("#", 1)[0].split("?", 1)[0])
        if not is_publication_article_url(href):
            continue
        key = slug_from_url(href)
        if not key or key in seen:
            continue
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        if len(title) < 12:
            continue
        seen.add(key)
        titled.append((m, key, href, title[:300]))

    for i, (m, key, href, title) in enumerate(titled):
        lo = titled[i - 1][0].end() if i else max(0, m.start() - 400)
        hi = titled[i + 1][0].start() if i + 1 < len(titled) else min(len(body), m.end() + 600)
        window_text = re.sub(r"<[^>]+>", " ", body[lo:hi])
        dm = _DATE_NEAR_RE.search(window_text)
        date_raw = dm.group(0) if dm else ""
        items.append(
            BcgListItem(
                source_key=key,
                url=href,
                title=title,
                published_at=parse_bcg_date(date_raw),
                publish_date_raw=date_raw,
            )
        )

    if items:
        return items

    # Fallback: href-only (title = slug).
    for m in _HREF_PUB_RE.finditer(body):
        href = urljoin(list_url, m.group(1).split("#", 1)[0].split("?", 1)[0])
        if not is_publication_article_url(href):
            continue
        key = slug_from_url(href)
        if not key or key in seen:
            continue
        seen.add(key)
        items.append(
            BcgListItem(
                source_key=key,
                url=href,
                title=key.split("/")[-1].replace("-", " ")[:300],
                published_at=None,
                publish_date_raw="",
            )
        )
    return items


def fetch_list_items(
    list_url: str,
    *,
    profile: str | BcgProfile | None = None,
    session: requests.Session | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[BcgListItem]:
    prof = profile if isinstance(profile, BcgProfile) else get_profile(profile)
    if not is_allowlisted_list_url(list_url, prof):
        raise BcgCaptureError(f"list_url not allowlisted for {prof.id}: {list_url}")
    sess = session or make_session()
    html = get_text(
        sess,
        list_url,
        headers={"Accept": "text/html,application/xhtml+xml,*/*", "Referer": HUB_URL},
        timeout=timeout,
    )
    if len(html) < 80:
        raise BcgBlockedError(f"empty list html {list_url}")
    return parse_list_html(html, list_url=list_url)


class _PdfHrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[tuple[str, str, str]] = []
        self._href: str | None = None
        self._aria = ""
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        ad = {k: (v or "") for k, v in attrs}
        href = ad.get("href") or ""
        if ".pdf" not in href.lower():
            return
        self._href = href
        self._aria = ad.get("aria-label") or ""
        self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.rows.append((self._href, self._aria, "".join(self._parts)))
            self._href = None

    @classmethod
    def extract(cls, html: str) -> list[tuple[str, str, str]]:
        p = cls()
        try:
            p.feed(html or "")
        except Exception:
            pass
        return p.rows


def find_pdf_url(detail_html: str, *, page_url: str) -> str | None:
    rows = _PdfHrefParser.extract(detail_html)
    if not rows:
        for href in re.findall(
            r'href=["\']([^"\']+\.pdf[^"\']*)["\']', detail_html, re.I
        ):
            rows.append((href, "", ""))
    resolved: list[str] = []
    for href, _aria, _text in rows:
        abs_url = urljoin(page_url, href.split("#", 1)[0])
        if re.search(r"\.pdf($|\?)", abs_url, re.I):
            resolved.append(abs_url)
    if not resolved:
        return None

    def score(u: str) -> tuple[int, int]:
        path = urlparse(u).path.lower()
        preferred = 0
        if "web-assets.bcg.com" in u.lower() or "/pdf-src/" in path:
            preferred += 4
        if "transcript" in path:
            preferred -= 5
        return (preferred, -len(u))

    resolved.sort(key=score, reverse=True)
    return resolved[0]


def parse_publish_date_from_html(html: str) -> date | None:
    m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html or "")
    if m:
        raw = m.group(1)
        # ISO or English
        iso = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
        if iso:
            try:
                return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
            except ValueError:
                pass
        d = parse_bcg_date(raw)
        if d:
            return d
    m = re.search(
        r'<time[^>]*(?:datetime=["\']([^"\']+)["\'])?[^>]*>\s*([^<]*)',
        html or "",
        re.I,
    )
    if m:
        for part in (m.group(1), m.group(2)):
            if not part:
                continue
            iso = re.match(r"(\d{4})-(\d{2})-(\d{2})", part)
            if iso:
                try:
                    return date(
                        int(iso.group(1)), int(iso.group(2)), int(iso.group(3))
                    )
                except ValueError:
                    pass
            d = parse_bcg_date(part)
            if d:
                return d
    return parse_bcg_date(re.sub(r"<[^>]+>", " ", html or "")[:8000])


def fetch_detail_meta(
    url: str,
    *,
    session: requests.Session | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    referer: str = LIST_URL,
) -> tuple[str | None, date | None]:
    if not is_publication_article_url(url):
        raise BcgCaptureError(f"not a publications article URL: {url}")
    sess = session or make_session()
    html = get_text(
        sess,
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml,*/*",
            "Referer": referer,
        },
        timeout=timeout,
    )
    _assert_not_denied(html[:4000], where=url)
    return find_pdf_url(html, page_url=url), parse_publish_date_from_html(html)


def download_pdf(
    url: str,
    dest_path: Any,
    *,
    session: requests.Session | None = None,
    timeout: float = 120.0,
    referer: str | None = None,
) -> int:
    path = Path(dest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sess = session or make_session()
    headers: dict[str, str] = {}
    if referer:
        headers["Referer"] = referer
    data = get_bytes(sess, url, headers=headers or None, timeout=timeout)
    head = data[:2000].decode("utf-8", errors="ignore")
    if _DENIED_RE.search(head):
        raise BcgBlockedError(f"access denied inside pdf {url}")
    if not data.startswith(b"%PDF"):
        raise BcgCaptureError(f"not a PDF ({url}): magic={data[:8]!r}")
    path.write_bytes(data)
    return len(data)


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


__all__ = [
    "BASE",
    "DEFAULT_PROFILE",
    "HUB_URL",
    "LIST_URL",
    "PROFILE_IDS",
    "PROFILES",
    "SOURCE",
    "BcgBlockedError",
    "BcgCaptureError",
    "BcgListItem",
    "BcgProfile",
    "download_pdf",
    "fetch_detail_meta",
    "fetch_list_items",
    "find_pdf_url",
    "get_profile",
    "is_allowlisted_list_url",
    "is_publication_article_url",
    "is_publications_hub",
    "make_session",
    "months_ago_cutoff",
    "normalize_list_url",
    "parse_list_html",
    "parse_publish_date_from_html",
    "pdf_page_count",
    "source_key_from_url",
]
