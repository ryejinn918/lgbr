"""Startup guards."""

from __future__ import annotations

import pytest

from lgbr_mcp import config


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "load_env", lambda: None)
    config.clear_config_caches()
    for key in (
        "LGBR_MCP_ENV",
        "LGBR_MCP_PUBLIC_BASE_URL",
        "LGBR_MCP_SIGNING_SECRET",
        "LGBR_MCP_OAUTH_USERNAME",
        "LGBR_MCP_OAUTH_PASSWORD",
        "LGBR_MCP_PDF_TTL_SECONDS",
        "LGBR_MCP_HOST",
        "LGBR_MCP_PORT",
    ):
        monkeypatch.delenv(key, raising=False)
    yield
    config.clear_config_caches()


def _set_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LGBR_MCP_SIGNING_SECRET", "s" * 20)
    monkeypatch.setenv("LGBR_MCP_OAUTH_USERNAME", "lgbr")
    monkeypatch.setenv("LGBR_MCP_OAUTH_PASSWORD", "secret")


def test_requires_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LGBR_MCP_PUBLIC_BASE_URL", "https://lgbrmcp.magpielabs.co.kr")
    with pytest.raises(SystemExit) as ei:
        config.validate_startup()
    assert ei.value.code == 2


def test_ok_with_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LGBR_MCP_PUBLIC_BASE_URL", "https://lgbrmcp.magpielabs.co.kr")
    _set_secrets(monkeypatch)
    config.validate_startup()


def test_pdf_ttl_default_900(monkeypatch: pytest.MonkeyPatch) -> None:
    assert config.pdf_ttl_seconds() == 900
