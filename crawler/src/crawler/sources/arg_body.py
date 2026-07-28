"""ARG articleView body fetch via curl-cffi."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from curl_cffi.requests import Session

from crawler.sources.arg_http import BASE, LIST_URL, get_html, make_session

SOURCE = "arg"
_CONTENT_RE = re.compile(
    r'<div id="article-view-content-div"[^>]*>(.*?)(?:\n<script|</div>\s*</article>)',
    flags=re.S | re.I,
)


@dataclass(frozen=True)
class ArgArticleBody:
    source_key: str
    url: str
    body_text: str
    status_code: int


def article_url(idxno: str) -> str:
    return urljoin(BASE, f"/news/articleView.html?idxno={idxno}")


def parse_body_html(html: str) -> str:
    """Extract plain text from #article-view-content-div."""
    m = _CONTENT_RE.search(html or "")
    if not m:
        return ""
    chunk = m.group(1)
    # Drop nested scripts if any leaked into the match.
    chunk = re.sub(r"<script\b[^>]*>.*?</script>", " ", chunk, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", chunk)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_article(
    idxno: str | None = None,
    *,
    url: str | None = None,
    client: Session | None = None,
) -> ArgArticleBody:
    """GET articleView and return parsed body_text."""
    key = (idxno or "").strip()
    if not key and url:
        m = re.search(r"idxno=(\d+)", url)
        if m:
            key = m.group(1)
    if not key:
        raise ValueError("idxno or url with idxno required")
    final_url = (url or "").strip() or article_url(key)

    own = client is None
    sess = client or make_session(accept="text/html,application/xhtml+xml")
    try:
        status, html = get_html(sess, final_url, referer=LIST_URL)
    finally:
        if own:
            sess.close()

    if status >= 400:
        raise RuntimeError(f"ARG article HTTP {status} for idxno={key}")
    body = parse_body_html(html)
    if not body:
        raise RuntimeError(f"ARG article body empty/unparsed for idxno={key}")
    return ArgArticleBody(
        source_key=key,
        url=final_url,
        body_text=body,
        status_code=status,
    )


def fetch_article_safe(
    idxno: str,
    *,
    url: str | None = None,
    client: Session | None = None,
) -> tuple[ArgArticleBody | None, str | None]:
    """Like fetch_article but returns (result, error_message)."""
    try:
        return fetch_article(idxno, url=url, client=client), None
    except Exception as exc:
        return None, str(exc)
