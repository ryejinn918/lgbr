"""Single shared-account OAuth AS for Claude connectors (username + password)."""

from __future__ import annotations

import hashlib
import hmac
import html
import secrets
import time
from typing import Any

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    RegistrationError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyHttpUrl
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

MCP_SCOPE = "mcp"
_ACCESS_TTL = 3600
_REFRESH_TTL = 86400 * 7
_CODE_TTL = 300
_MAX_CLIENTS = 64
_MAX_TOKENS = 256
_MAX_LOGIN_FAILURES = 8

# Open redirect / DCR abuse: only Claude hosted connector callback.
_ALLOWED_REDIRECT_URIS = frozenset(
    {
        "https://claude.ai/api/mcp/auth_callback",
    }
)


def _secret_eq(a: str, b: str) -> bool:
    """Length-independent compare for passwords/usernames."""
    return hmac.compare_digest(
        hashlib.sha256(a.encode("utf-8")).digest(),
        hashlib.sha256(b.encode("utf-8")).digest(),
    )


class SimpleOAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    """In-memory OAuth: one username/password, DCR, PKCE, refresh."""

    def __init__(
        self,
        *,
        username: str,
        password: str,
        login_url: str,
        scope: str = MCP_SCOPE,
    ) -> None:
        self.username = username
        self.password = password
        self.login_url = login_url.rstrip("/")
        self.scope = scope
        self.clients: dict[str, OAuthClientInformationFull] = {}
        self.auth_codes: dict[str, AuthorizationCode] = {}
        self.tokens: dict[str, AccessToken] = {}
        self.refresh_tokens: dict[str, RefreshToken] = {}
        self.state_mapping: dict[str, dict[str, Any]] = {}

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            raise ValueError("No client_id provided")
        for uri in client_info.redirect_uris:
            if str(uri).rstrip("/") not in _ALLOWED_REDIRECT_URIS:
                raise RegistrationError(
                    error="invalid_redirect_uri",
                    error_description="redirect_uri is not allowed",
                )
        if len(self.clients) >= _MAX_CLIENTS:
            # Drop oldest registrations (insertion order).
            for old_id in list(self.clients)[: max(1, len(self.clients) - _MAX_CLIENTS + 1)]:
                del self.clients[old_id]
        self.clients[client_info.client_id] = client_info

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        login_state = secrets.token_hex(16)
        self.state_mapping[login_state] = {
            "redirect_uri": str(params.redirect_uri),
            "code_challenge": params.code_challenge,
            "redirect_uri_provided_explicitly": str(
                params.redirect_uri_provided_explicitly
            ),
            "client_id": client.client_id,
            "resource": params.resource,
            "oauth_state": params.state,
            "failures": 0,
        }
        return f"{self.login_url}?state={login_state}"

    async def get_login_page(self, state: str) -> HTMLResponse:
        if not state or state not in self.state_mapping:
            raise HTTPException(400, "Invalid or missing state")
        safe_state = html.escape(state, quote=True)
        html_content = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><title>LGBR MCP 로그인</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:420px;margin:48px auto;padding:0 16px}}
label{{display:block;margin:.75rem 0 .25rem}}
input{{width:100%;padding:.5rem;box-sizing:border-box}}
button{{margin-top:1rem;padding:.6rem 1rem;width:100%;cursor:pointer}}
</style></head><body>
<h1>LGBR MCP</h1>
<p>Claude 커넥터 연결용 계정으로 로그인하세요.</p>
<form method="post" action="{html.escape(self.login_url, quote=True)}">
<input type="hidden" name="state" value="{safe_state}"/>
<label>Username<input name="username" autocomplete="username" required/></label>
<label>Password<input name="password" type="password" autocomplete="current-password" required/></label>
<button type="submit">Sign in</button>
</form></body></html>"""
        return HTMLResponse(html_content)

    async def handle_login_callback(self, request: Request) -> Response:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        state = form.get("state")
        if not isinstance(username, str) or not isinstance(password, str) or not isinstance(
            state, str
        ):
            raise HTTPException(400, "Missing username, password, or state")
        redirect_uri = await self._complete_login(username, password, state)
        return RedirectResponse(url=redirect_uri, status_code=302)

    async def _complete_login(self, username: str, password: str, state: str) -> str:
        state_data = self.state_mapping.get(state)
        if not state_data:
            raise HTTPException(400, "Invalid state parameter")

        if not _secret_eq(username, self.username) or not _secret_eq(
            password, self.password
        ):
            failures = int(state_data.get("failures") or 0) + 1
            state_data["failures"] = failures
            if failures >= _MAX_LOGIN_FAILURES:
                del self.state_mapping[state]
            raise HTTPException(401, "Invalid credentials")

        redirect_uri = state_data["redirect_uri"]
        code_challenge = state_data["code_challenge"]
        client_id = state_data["client_id"]
        resource = state_data.get("resource")
        oauth_state = state_data.get("oauth_state")
        if not isinstance(redirect_uri, str) or not isinstance(code_challenge, str):
            raise HTTPException(400, "Invalid state")
        if not isinstance(client_id, str):
            raise HTTPException(400, "Invalid state")
        if redirect_uri.rstrip("/") not in _ALLOWED_REDIRECT_URIS:
            raise HTTPException(400, "Invalid redirect_uri")

        code = secrets.token_urlsafe(32)
        self.auth_codes[code] = AuthorizationCode(
            code=code,
            client_id=client_id,
            redirect_uri=AnyHttpUrl(redirect_uri),
            redirect_uri_provided_explicitly=state_data[
                "redirect_uri_provided_explicitly"
            ]
            == "True",
            expires_at=time.time() + _CODE_TTL,
            scopes=[self.scope],
            code_challenge=code_challenge,
            resource=resource if isinstance(resource, str) else None,
            subject=username,
        )
        del self.state_mapping[state]
        return construct_redirect_uri(
            redirect_uri,
            code=code,
            state=oauth_state if isinstance(oauth_state, str) else None,
        )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        code = self.auth_codes.get(authorization_code)
        if not code:
            return None
        if code.expires_at < time.time():
            del self.auth_codes[authorization_code]
            return None
        if code.client_id != client.client_id:
            return None
        return code

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        if authorization_code.code not in self.auth_codes:
            raise ValueError("Invalid authorization code")
        if not client.client_id:
            raise ValueError("No client_id provided")
        del self.auth_codes[authorization_code.code]
        return self._issue_tokens(
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            resource=authorization_code.resource,
            subject=authorization_code.subject,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        access = self.tokens.get(token)
        if not access:
            return None
        if access.expires_at and access.expires_at < time.time():
            del self.tokens[token]
            return None
        return access

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        rt = self.refresh_tokens.get(refresh_token)
        if not rt or rt.client_id != client.client_id:
            return None
        if rt.expires_at and rt.expires_at < int(time.time()):
            del self.refresh_tokens[refresh_token]
            return None
        return rt

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        if refresh_token.token not in self.refresh_tokens:
            raise ValueError("Invalid refresh token")
        del self.refresh_tokens[refresh_token.token]
        for tok, at in list(self.tokens.items()):
            if at.client_id == client.client_id and at.subject == refresh_token.subject:
                del self.tokens[tok]
        return self._issue_tokens(
            client_id=client.client_id or refresh_token.client_id,
            scopes=scopes or refresh_token.scopes,
            resource=None,
            subject=refresh_token.subject,
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        self.tokens.pop(token.token, None)
        self.refresh_tokens.pop(token.token, None)

    def _issue_tokens(
        self,
        *,
        client_id: str,
        scopes: list[str],
        resource: str | None,
        subject: str | None,
    ) -> OAuthToken:
        self._trim_tokens()
        access = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(32)
        now = int(time.time())
        self.tokens[access] = AccessToken(
            token=access,
            client_id=client_id,
            scopes=scopes,
            expires_at=now + _ACCESS_TTL,
            resource=resource,
            subject=subject,
        )
        self.refresh_tokens[refresh] = RefreshToken(
            token=refresh,
            client_id=client_id,
            scopes=scopes,
            expires_at=now + _REFRESH_TTL,
            subject=subject,
        )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=_ACCESS_TTL,
            scope=" ".join(scopes),
            refresh_token=refresh,
        )

    def _trim_tokens(self) -> None:
        overflow = len(self.tokens) + len(self.refresh_tokens) - _MAX_TOKENS
        if overflow <= 0:
            return
        for key in list(self.tokens)[:overflow]:
            del self.tokens[key]
