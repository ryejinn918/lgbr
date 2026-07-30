"""Startup guards and API key policy."""

from __future__ import annotations

import pytest

from lgbr_mcp import config


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch):
    """Do not pull real repo .env into assertions."""
    monkeypatch.setattr(config, "load_env", lambda: None)
    config.clear_config_caches()
    for key in (
        "LGBR_MCP_ENV",
        "LGBR_MCP_PUBLIC_BASE_URL",
        "LGBR_MCP_API_KEY",
        "LGBR_MCP_SIGNING_SECRET",
        "LGBR_MCP_ALLOW_INSECURE",
        "LGBR_MCP_PDF_TTL_SECONDS",
        "LGBR_MCP_HOST",
        "LGBR_MCP_PORT",
    ):
        monkeypatch.delenv(key, raising=False)
    yield
    config.clear_config_caches()


def test_production_https_requires_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LGBR_MCP_PUBLIC_BASE_URL", "https://lgbrmcp.magpielabs.co.kr")
    with pytest.raises(SystemExit) as ei:
        config.validate_startup()
    assert ei.value.code == 2


def test_production_ok_with_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LGBR_MCP_PUBLIC_BASE_URL", "https://lgbrmcp.magpielabs.co.kr")
    monkeypatch.setenv("LGBR_MCP_API_KEY", "k" * 20)
    monkeypatch.setenv("LGBR_MCP_SIGNING_SECRET", "s" * 20)
    config.validate_startup()
    assert config.require_mcp_api_key() is True


def test_insecure_forbidden_under_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LGBR_MCP_PUBLIC_BASE_URL", "https://lgbrmcp.magpielabs.co.kr")
    monkeypatch.setenv("LGBR_MCP_API_KEY", "k" * 20)
    monkeypatch.setenv("LGBR_MCP_SIGNING_SECRET", "s" * 20)
    monkeypatch.setenv("LGBR_MCP_ALLOW_INSECURE", "1")
    with pytest.raises(SystemExit):
        config.validate_startup()


def test_local_insecure_skips_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LGBR_MCP_PUBLIC_BASE_URL", "http://127.0.0.1:8788")
    monkeypatch.setenv("LGBR_MCP_ALLOW_INSECURE", "1")
    config.validate_startup()
    assert config.require_mcp_api_key() is False


def test_pdf_ttl_default_900(monkeypatch: pytest.MonkeyPatch) -> None:
    assert config.pdf_ttl_seconds() == 900
