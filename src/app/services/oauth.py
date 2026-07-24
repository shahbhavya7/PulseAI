"""OAuth provider registry (Authlib).

Registers Google and Apple as OIDC clients, but **only when their credentials
are configured** — so the app runs with just Google set up, and Apple appears
only once its four env vars are present. Apple's client secret is a short-lived
JWT generated from the .p8 key (Apple doesn't use a static secret); we mint it
lazily via a `client_secret` callable so it's always fresh.
"""

from __future__ import annotations

import time
from functools import lru_cache

import jwt
from authlib.integrations.starlette_client import OAuth

from app.core.config import get_settings

GOOGLE_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"
APPLE_METADATA_URL = "https://appleid.apple.com/.well-known/openid-configuration"


def _apple_client_secret() -> str:
    """Generate Apple's client secret — a JWT signed with the .p8 key (ES256).

    Valid for a short window; regenerated on each call so it never goes stale.
    """
    settings = get_settings()
    assert settings.apple_private_key is not None  # guarded by apple_enabled
    now = int(time.time())
    headers = {"kid": settings.apple_key_id}
    payload = {
        "iss": settings.apple_team_id,
        "iat": now,
        "exp": now + 60 * 30,  # 30 min
        "aud": "https://appleid.apple.com",
        "sub": settings.apple_client_id,
    }
    return jwt.encode(
        payload,
        settings.apple_private_key.get_secret_value(),
        algorithm="ES256",
        headers=headers,
    )


@lru_cache(maxsize=1)
def get_oauth() -> OAuth:
    """Build the process-wide Authlib registry with the enabled providers."""
    settings = get_settings()
    oauth = OAuth()

    if settings.google_enabled:
        oauth.register(
            name="google",
            client_id=settings.google_client_id,
            client_secret=(
                settings.google_client_secret.get_secret_value()
                if settings.google_client_secret
                else None
            ),
            server_metadata_url=GOOGLE_METADATA_URL,
            client_kwargs={"scope": "openid email profile"},
        )

    if settings.apple_enabled:
        oauth.register(
            name="apple",
            client_id=settings.apple_client_id,
            # A callable secret is re-evaluated per request → always a fresh JWT.
            client_secret=_apple_client_secret,
            server_metadata_url=APPLE_METADATA_URL,
            client_kwargs={
                "scope": "openid email name",
                # Apple requires form_post when the name/email scope is requested.
                "response_mode": "form_post",
            },
        )

    return oauth


def enabled_providers() -> list[str]:
    """Names of the providers that are configured and usable."""
    settings = get_settings()
    providers: list[str] = []
    if settings.google_enabled:
        providers.append("google")
    if settings.apple_enabled:
        providers.append("apple")
    return providers
