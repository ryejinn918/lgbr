"""Environment for lgbr-mcp."""

from __future__ import annotations

import os
import sys
from functools import lru_cache

from dotenv import load_dotenv
from lgbr_api.db import load_database_env

_DEFAULT_PDF_TTL = 900  # 15 minutes (external-facing default)


def load_env() -> None:
    load_database_env()
    load_dotenv()


def is_production() -> bool:
    load_env()
    if (os.environ.get("LGBR_MCP_ENV") or "").strip().lower() == "production":
        return True
    base = (os.environ.get("LGBR_MCP_PUBLIC_BASE_URL") or "").strip().lower()
    return base.startswith("https://")


def validate_startup() -> None:
    """Fail fast when required secrets are missing."""
    load_env()
    missing: list[str] = []
    if not (os.environ.get("LGBR_MCP_SIGNING_SECRET") or "").strip():
        missing.append("LGBR_MCP_SIGNING_SECRET")
    if not (os.environ.get("LGBR_MCP_OAUTH_USERNAME") or "").strip():
        missing.append("LGBR_MCP_OAUTH_USERNAME")
    if not (os.environ.get("LGBR_MCP_OAUTH_PASSWORD") or "").strip():
        missing.append("LGBR_MCP_OAUTH_PASSWORD")
    if is_production() and not (os.environ.get("LGBR_MCP_PUBLIC_BASE_URL") or "").strip():
        missing.append("LGBR_MCP_PUBLIC_BASE_URL")
    if missing:
        print(
            "lgbr-mcp: missing required secrets: " + ", ".join(missing),
            file=sys.stderr,
        )
        raise SystemExit(2)


@lru_cache(maxsize=1)
def public_base_url() -> str:
    load_env()
    base = (os.environ.get("LGBR_MCP_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if base:
        return base
    host = (os.environ.get("LGBR_MCP_HOST") or "127.0.0.1").strip()
    port = (os.environ.get("LGBR_MCP_PORT") or "8788").strip()
    return f"http://{host}:{port}"


@lru_cache(maxsize=1)
def signing_secret() -> bytes:
    load_env()
    raw = (os.environ.get("LGBR_MCP_SIGNING_SECRET") or "").strip()
    if not raw:
        raise RuntimeError("LGBR_MCP_SIGNING_SECRET is not set")
    return raw.encode("utf-8")


def pdf_ttl_seconds() -> int:
    load_env()
    try:
        n = int(os.environ.get("LGBR_MCP_PDF_TTL_SECONDS") or str(_DEFAULT_PDF_TTL))
    except ValueError:
        n = _DEFAULT_PDF_TTL
    return max(60, min(n, 86400))


def oauth_username() -> str:
    load_env()
    return (os.environ.get("LGBR_MCP_OAUTH_USERNAME") or "").strip()


def oauth_password() -> str:
    load_env()
    return (os.environ.get("LGBR_MCP_OAUTH_PASSWORD") or "").strip()


def allowed_hosts() -> list[str]:
    load_env()
    raw = (os.environ.get("LGBR_MCP_ALLOWED_HOSTS") or "").strip()
    if not raw:
        return []
    return [h.strip() for h in raw.split(",") if h.strip()]


def clear_config_caches() -> None:
    public_base_url.cache_clear()
    signing_secret.cache_clear()
