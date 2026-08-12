"""OAuth provider tests."""

from __future__ import annotations

import asyncio

import pytest
from mcp.server.auth.provider import AuthorizationParams, RegistrationError
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl
from starlette.exceptions import HTTPException

from lgbr_mcp.oauth_provider import SimpleOAuthProvider, _is_allowed_redirect_uri


def _provider() -> SimpleOAuthProvider:
    return SimpleOAuthProvider(
        username="lgbr",
        password="secret",
        login_url="https://mcp.lgbr-ai.com/login",
    )


def _client(client_id: str, redirect_uri: str, name: str) -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id=client_id,
        redirect_uris=[AnyUrl(redirect_uri)],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
        client_name=name,
    )


def test_rejects_unknown_redirect() -> None:
    provider = _provider()
    client = _client("bad", "https://evil.example/callback", "evil")

    async def _run() -> None:
        with pytest.raises(RegistrationError):
            await provider.register_client(client)

    asyncio.run(_run())


@pytest.mark.parametrize(
    "uri",
    [
        "https://claude.ai/api/mcp/auth_callback",
        "https://chatgpt.com/connector_platform_oauth_redirect",
        "https://chatgpt.com/connector/oauth/abc123",
    ],
)
def test_allows_known_host_redirects(uri: str) -> None:
    assert _is_allowed_redirect_uri(uri)
    provider = _provider()
    client = _client("ok", uri, "host")

    async def _run() -> None:
        await provider.register_client(client)

    asyncio.run(_run())


@pytest.mark.parametrize(
    "uri",
    [
        "https://evil.example/callback",
        "https://chatgpt.com/connector/oauth/",
        "https://chatgpt.com/connector/oauth",
        "https://chatgpt.com/connector/oauth/../evil",
        "https://chatgpt.com/connector/oauth/abc/extra",
        "https://chatgpt.com.evil.example/connector/oauth/x",
    ],
)
def test_rejects_disallowed_redirect_uris(uri: str) -> None:
    assert not _is_allowed_redirect_uri(uri)


def test_login_issues_access_token() -> None:
    provider = _provider()
    redirect = "https://claude.ai/api/mcp/auth_callback"
    client = _client("ok", redirect, "claude")

    async def _run() -> None:
        await provider.register_client(client)
        url = await provider.authorize(
            client,
            AuthorizationParams(
                state="st",
                scopes=["mcp"],
                code_challenge="challenge",
                redirect_uri=AnyUrl(redirect),
                redirect_uri_provided_explicitly=True,
                resource="https://mcp.lgbr-ai.com/mcp/collect",
            ),
        )
        state = url.split("state=")[1]
        with pytest.raises(HTTPException):
            await provider._complete_login("lgbr", "wrong", state)
        redirect_url = await provider._complete_login("lgbr", "secret", state)
        assert isinstance(redirect_url, str)
        code = redirect_url.split("code=")[1].split("&")[0]
        auth_code = await provider.load_authorization_code(client, code)
        assert auth_code is not None
        token = await provider.exchange_authorization_code(client, auth_code)
        assert await provider.load_access_token(token.access_token) is not None

    asyncio.run(_run())


def test_chatgpt_redirect_login_completes() -> None:
    provider = _provider()
    redirect = "https://chatgpt.com/connector/oauth/cb_test"
    client = _client("gpt", redirect, "chatgpt")

    async def _run() -> None:
        await provider.register_client(client)
        url = await provider.authorize(
            client,
            AuthorizationParams(
                state="st",
                scopes=["mcp"],
                code_challenge="challenge",
                redirect_uri=AnyUrl(redirect),
                redirect_uri_provided_explicitly=True,
                resource="https://mcp.lgbr-ai.com/mcp/consensus",
            ),
        )
        state = url.split("state=")[1]
        redirect_url = await provider._complete_login("lgbr", "secret", state)
        assert isinstance(redirect_url, str)
        assert redirect_url.startswith(redirect)

    asyncio.run(_run())


def test_completed_state_replay_returns_done_page() -> None:
    provider = _provider()
    redirect = "https://claude.ai/api/mcp/auth_callback"
    client = _client("ok", redirect, "claude")

    async def _run() -> None:
        await provider.register_client(client)
        url = await provider.authorize(
            client,
            AuthorizationParams(
                state="st",
                scopes=["mcp"],
                code_challenge="challenge",
                redirect_uri=AnyUrl(redirect),
                redirect_uri_provided_explicitly=True,
                resource="https://mcp.lgbr-ai.com/mcp/collect",
            ),
        )
        state = url.split("state=")[1]
        first = await provider._complete_login("lgbr", "secret", state)
        assert isinstance(first, str) and "code=" in first
        assert await provider._complete_login("lgbr", "secret", state) is None
        page = await provider.get_login_page(state)
        assert page.status_code == 200
        body = page.body.decode()
        assert "window.close" in body
        assert "연결 완료" in body

    asyncio.run(_run())


def test_unknown_state_login_page_is_friendly_expired() -> None:
    provider = _provider()

    async def _run() -> None:
        page = await provider.get_login_page("missing-state")
        assert page.status_code == 400
        body = page.body.decode()
        assert "만료" in body or "다시 시도" in body
        assert "Invalid" not in body

    asyncio.run(_run())
