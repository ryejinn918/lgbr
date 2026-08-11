"""Nikkei list expansion via wor.jp section RSS (+ category HTML fallback)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from curl_cffi.requests import Session

from crawler.sources.browser_http import get_text, make_session
from crawler.sources.nikkei_sections import NikkeiSection, get_section

SOURCE = "nikkei"
PUBLISHER = "日本経済新聞"
JST = ZoneInfo("Asia/Tokyo")

_NS = {
    "rss": "http://purl.org/rss/1.0/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dc": "http://purl.org/dc/elements/1.1/",
}
_ARTICLE_KEY_RE = re.compile(
    r"/article/(DGXZQO[A-Z0-9_]+)/?",
    flags=re.I,
)
_ARTICLE_HREF_RE = re.compile(
    r'href=["\']((?:https?://www\.nikkei\.com)?/article/(DGXZQO[A-Z0-9_]+)/?[^"\']*)["\'][^>]*>(.*?)</a>',
    flags=re.I | re.S,
)


@dataclass(frozen=True)
class NikkeiListItem:
    source_key: str
    title: str
    url: str
    published_at: datetime | None
    section: str


def article_key_from_url(url: str) -> str | None:
    m = _ARTICLE_KEY_RE.search(url or "")
    return m.group(1).upper() if m else None


def canonical_article_url(source_key: str) -> str:
    return f"https://www.nikkei.com/article/{source_key}/"


def _parse_dc_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = raw.strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return None
    if dt.tzinfo is None:
        # wor.jp / Nikkei W3CDTF without offset is Japan local time.
        dt = dt.replace(tzinfo=JST)
    return dt.astimezone(timezone.utc)


def _local_tag(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def parse_rss_rdf(xml_text: str, *, section_id: str) -> list[NikkeiListItem]:
    """Parse RSS 1.0 RDF feed into list items (newest first as in feed)."""
    root = ET.fromstring(xml_text)
    items: list[NikkeiListItem] = []
    seen: set[str] = set()

    for el in root.iter():
        if _local_tag(el.tag) != "item":
            continue
        title = ""
        link = ""
        published: datetime | None = None
        for child in list(el):
            name = _local_tag(child.tag)
            text = (child.text or "").strip()
            if name == "title":
                title = text
            elif name == "link":
                link = text
            elif name == "date":
                published = _parse_dc_date(text)
        about = el.attrib.get(f"{{{_NS['rdf']}}}about") or link
        key = article_key_from_url(about) or article_key_from_url(link)
        if not key or key in seen:
            continue
        if not title:
            continue
        seen.add(key)
        items.append(
            NikkeiListItem(
                source_key=key,
                title=title,
                url=canonical_article_url(key),
                published_at=published,
                section=section_id,
            )
        )
    return items


def parse_category_html(html: str, *, section_id: str) -> list[NikkeiListItem]:
    """Extract article links from a category page (title may be sparse)."""
    items: list[NikkeiListItem] = []
    seen: set[str] = set()
    for m in _ARTICLE_HREF_RE.finditer(html or ""):
        key = m.group(2).upper()
        if key in seen:
            continue
        raw_title = re.sub(r"<[^>]+>", " ", m.group(3) or "")
        title = re.sub(r"\s+", " ", raw_title).strip()
        title = re.sub(r"\s+\d{1,2}:\d{2}$", "", title).strip() or key
        seen.add(key)
        items.append(
            NikkeiListItem(
                source_key=key,
                title=title,
                url=canonical_article_url(key),
                published_at=None,
                section=section_id,
            )
        )
    return items


def make_nikkei_session(*, accept: str = "application/rdf+xml,*/*") -> Session:
    return make_session(
        referer="https://www.nikkei.com/",
        origin="https://www.nikkei.com",
        accept=accept,
    )


def fetch_rss_items(
    section: NikkeiSection | str,
    *,
    client: Session | None = None,
) -> list[NikkeiListItem]:
    sec = section if isinstance(section, NikkeiSection) else get_section(section)
    own = client is None
    sess = client or make_nikkei_session()
    try:
        xml_text = get_text(sess, sec.rss_url)
    finally:
        if own:
            sess.close()
    return parse_rss_rdf(xml_text, section_id=sec.id)


def fetch_category_items(
    section: NikkeiSection | str,
    *,
    client: Session | None = None,
) -> list[NikkeiListItem]:
    sec = section if isinstance(section, NikkeiSection) else get_section(section)
    own = client is None
    sess = client or make_nikkei_session(accept="text/html,application/xhtml+xml")
    try:
        html = get_text(sess, sec.category_url)
    finally:
        if own:
            sess.close()
    return parse_category_html(html, section_id=sec.id)


def merge_list_items(
    primary: list[NikkeiListItem],
    secondary: list[NikkeiListItem],
) -> list[NikkeiListItem]:
    """Prefer primary metadata; append secondary keys not already seen."""
    by_key: dict[str, NikkeiListItem] = {}
    order: list[str] = []
    for item in primary + secondary:
        existing = by_key.get(item.source_key)
        if existing is None:
            by_key[item.source_key] = item
            order.append(item.source_key)
            continue
        # Upgrade placeholder title / missing date from the other source.
        title = existing.title
        if title == existing.source_key and item.title != item.source_key:
            title = item.title
        published = existing.published_at or item.published_at
        by_key[item.source_key] = NikkeiListItem(
            source_key=existing.source_key,
            title=title,
            url=existing.url,
            published_at=published,
            section=existing.section or item.section,
        )
    return [by_key[k] for k in order]


def fetch_section_items(
    section_id: str,
    *,
    client: Session | None = None,
    include_category_html: bool = True,
) -> dict[str, Any]:
    """Fetch RSS (+ optional category HTML). Returns items and source flags."""
    sec = get_section(section_id)
    own = client is None
    sess = client or make_nikkei_session()
    rss_ok = False
    html_ok = False
    rss_items: list[NikkeiListItem] = []
    html_items: list[NikkeiListItem] = []
    errors: list[str] = []
    try:
        try:
            rss_items = fetch_rss_items(sec, client=sess)
            rss_ok = True
        except Exception as exc:
            errors.append(f"rss: {exc}")
        if include_category_html:
            try:
                html_items = fetch_category_items(sec, client=sess)
                html_ok = True
            except Exception as exc:
                errors.append(f"category_html: {exc}")
    finally:
        if own:
            sess.close()

    if not rss_ok and not html_ok:
        raise RuntimeError(
            f"nikkei section {sec.id} list failed: {'; '.join(errors)}"
        )
    items = merge_list_items(rss_items, html_items)
    return {
        "section": sec.id,
        "rss_ok": rss_ok,
        "html_ok": html_ok,
        "rss_count": len(rss_items),
        "html_count": len(html_items),
        "items": items,
        "errors": errors,
        "host": urlparse(sec.rss_url).netloc,
    }
