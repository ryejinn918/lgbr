"""OAuth provider tests."""

from __future__ import annotations

import asyncio

import pytest
from mcp.server.auth.provider import AuthorizationParams, RegistrationError
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl
from starlette.exceptions import HTTPException

from lgbr_mcp.oauth_provider import SimpleOAuthProvider


def _provider() -> SimpleOAuthProvider:
    return SimpleOAuthProvider(
        username="lgbr",
        password="secret",
        login_url="https://lgbrmcp.magpielabs.co.kr/login",
    )


def test_rejects_non_claude_redirect() -> None:
    provider = _provider()
    client = OAuthClientInformationFull(
        client_id="bad",
        redirect_uris=[AnyUrl("https://evil.example/callback")],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
        client_name="evil",
    )

    async def _run() -> None:
        with pytest.raises(RegistrationError):
            await provider.register_client(client)

    asyncio.run(_run())


def test_login_issues_access_token() -> None:
    provider = _provider()
    client = OAuthClientInformationFull(
        client_id="ok",
        redirect_uris=[AnyUrl("https://claude.ai/api/mcp/auth_callback")],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
        client_name="claude",
    )

    async def _run() -> None:
        await provider.register_client(client)
        url = await provider.authorize(
            client,
            AuthorizationParams(
                state="st",
                scopes=["mcp"],
                code_challenge="challenge",
                redirect_uri=AnyUrl("https://claude.ai/api/mcp/auth_callback"),
                redirect_uri_provided_explicitly=True,
                resource="https://lgbrmcp.magpielabs.co.kr/mcp/collect",
            ),
        )
        state = url.split("state=")[1]
        with pytest.raises(HTTPException):
            await provider._complete_login("lgbr", "wrong", state)
        redirect = await provider._complete_login("lgbr", "secret", state)
        code = redirect.split("code=")[1].split("&")[0]
        auth_code = await provider.load_authorization_code(client, code)
        assert auth_code is not None
        token = await provider.exchange_authorization_code(client, auth_code)
        assert await provider.load_access_token(token.access_token) is not None

    asyncio.run(_run())
