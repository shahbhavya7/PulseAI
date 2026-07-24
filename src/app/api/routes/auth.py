"""Authentication endpoints — Google / Apple OIDC sign-in.

Flow (browser):

1. ``GET  /auth/providers`` — which buttons to show.
2. ``GET  /auth/login/{provider}`` — 302 to the provider's consent screen.
3. Provider redirects back to ``/auth/callback/{provider}`` (GET for Google,
   POST form_post for Apple) → we verify the id-token, upsert the user, set the
   session cookie, and 302 to the frontend.
4. ``GET  /auth/me`` — the current user (401 if not signed in).
5. ``POST /auth/logout`` — clears the session cookie.

Any provider/consent failure lands on the frontend sign-in page with
``?error=…`` rather than crashing.
"""

from __future__ import annotations

from typing import Any

from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.auth import CurrentUserResponse, ProvidersResponse
from app.services.auth import (
    clear_session_cookie,
    set_session_cookie,
    upsert_oauth_user,
)
from app.services.oauth import enabled_providers, get_oauth

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _redirect_uri(provider: str) -> str:
    """The absolute callback URL registered with the provider."""
    settings = get_settings()
    base = settings.backend_base_url.rstrip("/")
    return f"{base}{settings.api_prefix}/auth/callback/{provider}"


def _frontend(path: str) -> str:
    return f"{get_settings().frontend_base_url.rstrip('/')}{path}"


@router.get("/providers", response_model=ProvidersResponse)
def list_providers() -> ProvidersResponse:
    """Return the configured sign-in providers (drives the sign-in buttons)."""
    return ProvidersResponse(providers=enabled_providers())


@router.get("/login/{provider}")
async def login(provider: str, request: Request) -> RedirectResponse:
    """Kick off the OAuth redirect to ``provider``."""
    if provider not in enabled_providers():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "provider_unavailable", "message": f"{provider} is not configured"},
        )
    client = get_oauth().create_client(provider)
    assert client is not None
    redirect: RedirectResponse = await client.authorize_redirect(
        request, _redirect_uri(provider)
    )
    return redirect


@router.api_route("/callback/{provider}", methods=["GET", "POST"])
async def callback(provider: str, request: Request, db: DbSession) -> RedirectResponse:
    """Handle the provider redirect: verify, upsert user, set cookie, bounce."""
    if provider not in enabled_providers():
        return RedirectResponse(_frontend("/signin?error=provider_unavailable"))

    client = get_oauth().create_client(provider)
    assert client is not None
    try:
        token = await client.authorize_access_token(request)
    except OAuthError as exc:
        # User denied consent, state mismatch, expired code, etc. — never crash.
        logger.info("OAuth callback failed for %s: %s", provider, exc.error)
        return RedirectResponse(_frontend(f"/signin?error={exc.error or 'oauth_failed'}"))

    claims: dict[str, Any] = token.get("userinfo") or {}
    subject = claims.get("sub")
    email = claims.get("email")
    if not subject or not email:
        # Apple only returns the name on the very first authorization; email/sub
        # always come in the id-token. Missing sub/email means we can't proceed.
        logger.warning("OAuth id-token missing sub/email for %s", provider)
        return RedirectResponse(_frontend("/signin?error=missing_claims"))

    full_name = claims.get("name") or _apple_name(token)
    user = upsert_oauth_user(
        db,
        provider=provider,
        subject=str(subject),
        email=str(email),
        full_name=full_name,
    )

    response = RedirectResponse(_frontend("/"), status_code=status.HTTP_302_FOUND)
    set_session_cookie(response, user)
    return response


def _apple_name(token: dict[str, Any]) -> str | None:
    """Apple sends the display name (once) in a ``user`` form field, not the
    id-token. Authlib surfaces raw form data on the token dict when present."""
    user_field = token.get("user")
    if isinstance(user_field, dict):
        name = user_field.get("name")
        if isinstance(name, dict):
            parts = [name.get("firstName"), name.get("lastName")]
            joined = " ".join(p for p in parts if p)
            return joined or None
    return None


@router.get("/me", response_model=CurrentUserResponse)
def me(user: CurrentUser) -> CurrentUserResponse:
    """Return the authenticated user (401 when not signed in)."""
    return CurrentUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=str(user.role),
        oauth_provider=user.oauth_provider,
    )


@router.post("/logout")
def logout() -> JSONResponse:
    """Clear the session cookie."""
    response = JSONResponse({"status": "signed_out"})
    clear_session_cookie(response)
    return response
