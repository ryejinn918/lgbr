"""Browser-like HTTP via curl-cffi (Chrome TLS impersonate).

Used by ARG / EY / PwC / Accenture / KPMG collectors so outbound requests
do not use bare urllib fingerprints. Always pass ``proxy=None`` so env
proxies cannot force a broken CONNECT tunnel.
"""

from __future__ import annotations

from typing import Any

from curl_cffi import requests

IMPERSONATE = "chrome"
DEFAULT_TIMEOUT = 30.0


def make_session(
    *,
    referer: str,
    origin: str | None = None,
    accept: str = "*/*",
) -> requests.Session:
    """Chrome-impersonating session with site referer defaults."""
    sess = requests.Session(impersonate=IMPERSONATE)
    headers: dict[str, str] = {
        "Accept": accept,
        "Referer": referer,
    }
    if origin:
        headers["Origin"] = origin
    sess.headers.update(headers)
    return sess


def get_bytes(
    sess: requests.Session,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> bytes:
    resp = sess.get(
        url,
        params=params,
        headers=headers,
        timeout=timeout,
        proxy=None,
    )
    resp.raise_for_status()
    return resp.content


def get_text(
    sess: requests.Session,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    return get_bytes(
        sess, url, headers=headers, params=params, timeout=timeout
    ).decode("utf-8", "ignore")


def get_json(
    sess: requests.Session,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    resp = sess.get(
        url,
        params=params,
        headers=headers,
        timeout=timeout,
        proxy=None,
    )
    resp.raise_for_status()
    return resp.json()


def post(
    sess: requests.Session,
    url: str,
    *,
    data: bytes | None = None,
    json: Any = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    """POST and return parsed JSON when Content-Type looks like JSON."""
    resp = sess.post(
        url,
        data=data,
        json=json,
        headers=headers,
        timeout=timeout,
        proxy=None,
    )
    resp.raise_for_status()
    ctype = (resp.headers.get("content-type") or "").lower()
    if "json" in ctype or resp.text.lstrip().startswith(("{", "[")):
        return resp.json()
    return resp.text
