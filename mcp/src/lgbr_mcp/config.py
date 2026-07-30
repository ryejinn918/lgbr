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


def allow_insecure() -> bool:
    load_env()
    return (os.environ.get("LGBR_MCP_ALLOW_INSECURE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def validate_startup() -> None:
    """Fail fast when secrets are missing for the current mode."""
    load_env()
    prod = is_production()
    insecure = allow_insecure()
    key = (os.environ.get("LGBR_MCP_API_KEY") or "").strip()
    signing = (os.environ.get("LGBR_MCP_SIGNING_SECRET") or "").strip()

    if prod and insecure:
        print(
            "lgbr-mcp: LGBR_MCP_ALLOW_INSECURE cannot be used when "
            "LGBR_MCP_ENV=production or PUBLIC_BASE_URL is https",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if prod:
        missing = []
        if not key:
            missing.append("LGBR_MCP_API_KEY")
        if not signing:
            missing.append("LGBR_MCP_SIGNING_SECRET")
        if missing:
            print(
                "lgbr-mcp: missing required secrets for public/https mode: "
                + ", ".join(missing),
                file=sys.stderr,
            )
            raise SystemExit(2)
        return

    # Local: API key and signing secret required unless ALLOW_INSECURE=1
    if not insecure:
        missing = []
        if not key:
            missing.append("LGBR_MCP_API_KEY")
        if not signing:
            missing.append("LGBR_MCP_SIGNING_SECRET")
        if missing:
            print(
                "lgbr-mcp: set "
                + ", ".join(missing)
                + " or LGBR_MCP_ALLOW_INSECURE=1 for local-only",
                file=sys.stderr,
            )
            raise SystemExit(2)


def require_mcp_api_key() -> bool:
    """Whether /mcp/* must present a valid API key."""
    if allow_insecure() and not is_production() and mcp_api_key() is None:
        return False
    return True


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
    if raw:
        return raw.encode("utf-8")
    if allow_insecure() and not is_production():
        return b"lgbr-mcp-dev-secret"
    raise RuntimeError("LGBR_MCP_SIGNING_SECRET is not set")


def pdf_ttl_seconds() -> int:
    load_env()
    try:
        n = int(os.environ.get("LGBR_MCP_PDF_TTL_SECONDS") or str(_DEFAULT_PDF_TTL))
    except ValueError:
        n = _DEFAULT_PDF_TTL
    return max(60, min(n, 86400))


def mcp_api_key() -> str | None:
    load_env()
    key = (os.environ.get("LGBR_MCP_API_KEY") or "").strip()
    return key or None


def allowed_hosts() -> list[str]:
    load_env()
    raw = (os.environ.get("LGBR_MCP_ALLOWED_HOSTS") or "").strip()
    if not raw:
        return []
    return [h.strip() for h in raw.split(",") if h.strip()]


def clear_config_caches() -> None:
    public_base_url.cache_clear()
    signing_secret.cache_clear()
