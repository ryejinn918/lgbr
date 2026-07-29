"""Shared curl-cffi Session for ARG list/body collectors."""

from __future__ import annotations

from typing import Any

from curl_cffi import requests

from crawler.sources.browser_http import (
    DEFAULT_TIMEOUT,
    get_json as _get_json,
    make_session as _make_session,
)

BASE = "https://www.arg.co.kr"
LIST_URL = f"{BASE}/news/articleList.html?view_type=sm"
AJAX_URL = f"{BASE}/news/ajaxArticlePaging.php"
# Re-export for existing imports.
IMPERSONATE = "chrome"


def make_session(*, accept: str = "application/json") -> requests.Session:
    """Chrome-impersonating session with ARG referer defaults."""
    return _make_session(referer=LIST_URL, accept=accept)


def get_json(
    sess: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    return _get_json(
        sess,
        url,
        params=params,
        headers={
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": LIST_URL,
        },
        timeout=timeout,
    )


def get_html(
    sess: requests.Session,
    url: str,
    *,
    referer: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[int, str]:
    resp = sess.get(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Referer": referer or BASE + "/",
        },
        timeout=timeout,
        proxy=None,
    )
    return resp.status_code, resp.text