"""HTTP helpers for KEA issue reports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import urljoin

from curl_cffi import requests

from crawler.sources.browser_http import DEFAULT_TIMEOUT, get_bytes, get_text, make_session

SOURCE = "kea"
BASE = "https://www.gokea.org"
LIST_URL = f"{BASE}/core/?cid=53"


@dataclass(frozen=True)
class KeaListItem:
    source_key: str
    title: str
    detail_url: str
    published_at: date | None


def fetch_list_page(page: int = 1, *, session: requests.Session | None = None, timeout: float = DEFAULT_TIMEOUT) -> list[KeaListItem]:
    if page < 1:
        raise ValueError("page must be >= 1")
    sess = session or make_session(referer=LIST_URL, origin=BASE)
    html = get_text(sess, LIST_URL, params={"page": str(page)}, timeout=timeout)
    pattern = re.compile(
        r'href=["\'](?P<href>[^"\']*cid=53[^"\']*uid=(?P<uid>\d+)[^"\']*)["\'][^>]*>(?P<body>.*?)</a>',
        re.I | re.S,
    )
    items: list[KeaListItem] = []
    seen: set[str] = set()
    for match in pattern.finditer(html):
        uid = match.group("uid")
        if uid in seen:
            continue
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", match.group("body"))).strip()
        if not title:
            continue
        items.append(KeaListItem(uid, title, urljoin(LIST_URL, match.group("href")), _date_near_uid(html, uid)))
        seen.add(uid)
    return items


def fetch_detail_pdf_url(item: KeaListItem, *, session: requests.Session | None = None, timeout: float = DEFAULT_TIMEOUT) -> str | None:
    sess = session or make_session(referer=LIST_URL, origin=BASE)
    html = get_text(sess, item.detail_url, timeout=timeout)
    for raw in re.findall(r"(?:href|src)=[\"']([^\"']+)[\"']", html, re.I):
        if ".pdf" in raw.lower() or "/bb/down" in raw.lower():
            return urljoin(BASE, raw.replace("&amp;", "&"))
    return None


def download_pdf(session: requests.Session, url: str, *, timeout: float = DEFAULT_TIMEOUT) -> bytes:
    return get_bytes(session, url, timeout=timeout)


def _date_near_uid(html: str, uid: str) -> date | None:
    pos = html.find(f"uid={uid}")
    text = re.sub(r"<[^>]+>", " ", html[max(0, pos - 1800) : pos + 1800]) if pos >= 0 else ""
    match = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", text)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None
