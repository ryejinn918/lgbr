"""Shared curl-cffi Session for ARG list/body collectors."""

from __future__ import annotations

from typing import Any

from curl_cffi import requests

BASE = "https://www.arg.co.kr"
LIST_URL = f"{BASE}/news/articleList.html?view_type=sm"
AJAX_URL = f"{BASE}/news/ajaxArticlePaging.php"
IMPERSONATE = "chrome"
DEFAULT_TIMEOUT = 30.0


def make_session(*, accept: str = "application/json") -> requests.Session:
    """Chrome-impersonating session with ARG referer defaults."""
    sess = requests.Session(impersonate=IMPERSONATE)
    sess.headers.update(
        {
            "Accept": accept,
            "Referer": LIST_URL,
        }
    )
    return sess


def get_json(
    sess: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    resp = sess.get(
        url,
        params=params,
        headers={
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": LIST_URL,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


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
    )
    return resp.status_code, resp.text
