"""Public landing page smoke checks."""

from __future__ import annotations

import asyncio

from starlette.testclient import TestClient

from lgbr_mcp.asgi import app, root_page
from lgbr_mcp.branding import landing_html
from lgbr_mcp.catalog import render_landing_html


def test_landing_html_has_favicon_connectors_tools() -> None:
    html = landing_html()
    assert "favicon.ico" in html
    assert "favicon.png" in html
    assert "favicon.svg" in html
    assert "https://mcp.lgbr-ai.com/mcp/collect" in html
    assert "https://mcp.lgbr-ai.com/mcp/consensus" in html
    assert "LGBR MCP" in html
    assert "Instructions" in html
    assert "search_reports" in html
    assert "get_report" in html
    assert "search_news" in html
    assert "get_consensus" in html
    assert "lgbr-consensus.get_consensus" in html
    assert "MagpieLabs" not in html
    assert "유료" not in html
    assert " paid " not in f" {html.lower()} "


def test_root_page_serves_landing() -> None:
    response = asyncio.run(root_page(None))  # type: ignore[arg-type]
    assert response.status_code == 200
    body = response.body.decode("utf-8")
    assert body == render_landing_html()


def test_get_root_and_favicons() -> None:
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        assert "https://mcp.lgbr-ai.com/mcp/collect" in r.text
        assert "search_reports" in r.text
        assert 'rel="icon" href="/favicon.ico"' in r.text

        for path, needle in (
            ("/favicon.ico", b""),
            ("/favicon.png", b"\x89PNG"),
            ("/favicon.svg", b"<svg"),
        ):
            fr = client.get(path)
            assert fr.status_code == 200, path
            if needle:
                assert needle in fr.content
