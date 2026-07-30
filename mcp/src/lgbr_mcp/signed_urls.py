"""HMAC-signed report PDF URLs (header-free GET for Claude)."""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

from lgbr_mcp.config import pdf_ttl_seconds, public_base_url, signing_secret


def sign_report_pdf_url(report_id: str, *, ttl_seconds: int | None = None) -> str:
    rid = (report_id or "").strip()
    ttl = pdf_ttl_seconds() if ttl_seconds is None else max(60, int(ttl_seconds))
    exp = int(time.time()) + ttl
    sig = _signature(rid, exp)
    qs = urlencode({"exp": str(exp), "sig": sig})
    return f"{public_base_url()}/files/reports/{rid}?{qs}"


def verify_report_signature(report_id: str, exp: str | None, sig: str | None) -> bool:
    rid = (report_id or "").strip()
    if not rid or not exp or not sig:
        return False
    try:
        exp_i = int(exp)
    except (TypeError, ValueError):
        return False
    if exp_i < int(time.time()):
        return False
    expected = _signature(rid, exp_i)
    return hmac.compare_digest(expected, sig.strip())


def _signature(report_id: str, exp: int) -> str:
    msg = f"{report_id}:{exp}".encode("utf-8")
    return hmac.new(signing_secret(), msg, hashlib.sha256).hexdigest()
