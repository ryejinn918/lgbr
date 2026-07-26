"""ARG (arg.co.kr) list-expansion feed — metadata only, no body scrape."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, urljoin
from zoneinfo import ZoneInfo

import httpx

SOURCE = "arg"
BASE = "https://www.arg.co.kr"
LIST_URL = f"{BASE}/news/articleList.html?view_type=sm"
AJAX_URL = f"{BASE}/news/ajaxArticlePaging.php"
KST = ZoneInfo("Asia/Seoul")

_USER_AGENT = "lgbr-feed/0.1 (+local; list-meta only)"


@dataclass(frozen=True)
class ArgListItem:
    source_key: str
    title: str
    url: str
    published_at: datetime | None
    section: str | None
    publisher: str | None


def fetch_page(
    page: int,
    *,
    client: httpx.Client | None = None,
    list_per_page: int = 20,
    total: str = "0",
) -> list[ArgListItem]:
    """Fetch one list page via ARG's JSON paging endpoint."""
    if page < 1:
        raise ValueError("page must be >= 1")
    params = {
        "total": total,
        "list_per_page": str(list_per_page),
        "page_per_page": "10",
        "page": str(page),
        "sc_section_code": "",
        "sc_sub_section_code": "",
        "sc_serial_code": "",
        "sc_area": "",
        "sc_level": "",
        "sc_article_type": "",
        "sc_view_level": "",
        "sc_sdate": "",
        "sc_edate": "",
        "sc_serial_number": "",
        "sc_word": "",
        "sc_word2": "",
        "sc_andor": "",
        "sc_order_by": "",
        "view_type": "sm",
        "sc_multi_code": "",
        "sc_is_image": "",
        "sc_is_movie": "",
        "sc_user_name": "",
        "box_idxno": "",
    }
    own = client is None
    http = client or httpx.Client(
        timeout=30.0,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
            "Referer": LIST_URL,
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    try:
        resp = http.get(AJAX_URL, params=params)
        resp.raise_for_status()
        payload = resp.json()
    finally:
        if own:
            http.close()

    if not isinstance(payload, dict) or payload.get("result") != "success":
        msg = ""
        if isinstance(payload, dict):
            msg = str(payload.get("msg") or "")
        raise RuntimeError(f"ARG ajax paging failed: {msg or payload!r}")

    rows = payload.get("data") or []
    if not isinstance(rows, list):
        return []
    items: list[ArgListItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        parsed = _parse_row(row)
        if parsed is not None:
            items.append(parsed)
    return items


def parse_list_html(html: str) -> list[ArgListItem]:
    """Fallback HTML parser for articleList (same meta fields, no body)."""
    items: list[ArgListItem] = []
    for block in re.findall(
        r'<li class="altlist-text-item">(.*?)</li>',
        html,
        flags=re.S | re.I,
    ):
        link = re.search(
            r'href="([^"]*articleView\.html\?idxno=(\d+)[^"]*)"',
            block,
            flags=re.I,
        )
        if not link:
            continue
        title_m = re.search(
            r'class="line-x1"[^>]*>\s*(.*?)\s*</a>',
            block,
            flags=re.S | re.I,
        )
        title = _clean_text(title_m.group(1) if title_m else "")
        info = re.findall(
            r'class="altlist-info-item"[^>]*>\s*(.*?)\s*</div>',
            block,
            flags=re.S | re.I,
        )
        section = _clean_text(info[0]) if len(info) >= 1 else None
        when = _clean_text(info[1]) if len(info) >= 2 else ""
        idxno = link.group(2)
        url = urljoin(BASE, link.group(1))
        items.append(
            ArgListItem(
                source_key=idxno,
                title=title or f"ARG {idxno}",
                url=url,
                published_at=_parse_list_datetime(when),
                section=section or None,
                publisher=section or None,
            )
        )
    return items


def _parse_row(row: dict[str, Any]) -> ArgListItem | None:
    idxno = str(row.get("idxno") or "").strip()
    if not idxno:
        return None
    title = _decode(row.get("title")) or f"ARG {idxno}"
    link = str(row.get("link_url") or f"/news/articleView.html?idxno={idxno}")
    url = urljoin(BASE, link)
    section = _decode(row.get("sectionTitle")) or None
    published = _published_at(row)
    return ArgListItem(
        source_key=idxno,
        title=title,
        url=url,
        published_at=published,
        section=section,
        publisher=section,
    )


def _published_at(row: dict[str, Any]) -> datetime | None:
    # List UI shows recognition (embargo) time when present.
    rec_d = str(row.get("recognition_date") or "").strip()
    rec_t = str(row.get("recognition_time") or "").strip()
    if rec_d and rec_t:
        dt = _combine_kst(rec_d, rec_t)
        if dt:
            return dt
    pub = str(row.get("pub_date") or "").strip()
    if pub:
        return _combine_kst(pub, "00:00:00")
    return None


def _combine_kst(date_s: str, time_s: str) -> datetime | None:
    date_s = date_s.strip()
    time_s = time_s.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            naive = datetime.strptime(f"{date_s} {time_s}", fmt)
            return naive.replace(tzinfo=KST).astimezone(timezone.utc)
        except ValueError:
            continue
    try:
        naive = datetime.strptime(date_s, "%Y-%m-%d")
        return naive.replace(tzinfo=KST).astimezone(timezone.utc)
    except ValueError:
        return None


def _parse_list_datetime(text: str) -> datetime | None:
    """Parse list display like '07-24 07:55' (KST, current/nearest year)."""
    text = _clean_text(text)
    m = re.match(r"^(\d{2})-(\d{2})\s+(\d{2}):(\d{2})$", text)
    if not m:
        return None
    month, day, hour, minute = (int(x) for x in m.groups())
    now = datetime.now(KST)
    year = now.year
    try:
        naive = datetime(year, month, day, hour, minute, tzinfo=KST)
    except ValueError:
        return None
    # If far in the future, roll back a year (year boundary).
    if naive > now.replace(tzinfo=KST) and (naive - now).days > 30:
        try:
            naive = naive.replace(year=year - 1)
        except ValueError:
            return None
    return naive.astimezone(timezone.utc)


def _decode(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    try:
        from urllib.parse import unquote

        return _clean_text(unquote(text.replace("+", " ")))
    except Exception:
        return _clean_text(text)


def _clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def ajax_query_url(page: int) -> str:
    """Debug helper."""
    return f"{AJAX_URL}?{urlencode({'page': page, 'view_type': 'sm'})}"
