# Phase 5 — Authentication (Google / Apple OIDC)

Replaces the Phase 1 dev-user stub (`X-User-Id` header) with **real sign-in**
via Google and Apple (OpenID Connect). After a successful login the backend
issues a signed **session JWT in an httpOnly cookie**; every route resolves the
acting user from that cookie and scopes all data to them.

## Where things live

### Backend

| File | Holds |
| --- | --- |
| [src/app/core/config.py](../src/app/core/config.py) | auth settings: `jwt_secret`, cookie flags, base URLs, Google/Apple creds; `google_enabled`/`apple_enabled` |
| [src/app/models/user.py](../src/app/models/user.py) | `oauth_provider` + `oauth_subject` columns; unique `(provider, subject)` |
| [alembic/versions/0004_user_oauth_identity.py](../alembic/versions/0004_user_oauth_identity.py) | migration for the above |
| [src/app/services/auth.py](../src/app/services/auth.py) | session JWTs (`issue`/`decode`), cookie set/clear, `upsert_oauth_user` |
| [src/app/services/oauth.py](../src/app/services/oauth.py) | Authlib registry; Google + Apple (config-gated); Apple client-secret JWT |
| [src/app/api/routes/auth.py](../src/app/api/routes/auth.py) | `/auth/providers`, `/auth/login/{p}`, `/auth/callback/{p}`, `/auth/me`, `/auth/logout` |
| [src/app/api/deps.py](../src/app/api/deps.py) | `get_current_user` — reads the session cookie → `User` (401 otherwise) |
| [src/app/schemas/auth.py](../src/app/schemas/auth.py) | `CurrentUserResponse`, `ProvidersResponse` |
| [src/app/main.py](../src/app/main.py) | `SessionMiddleware` (OAuth state) + auth router; dev-seed removed |
| [tests/test_auth.py](../tests/test_auth.py) | JWT round-trip, endpoint 401s, provisioning, isolation |
| [tests/conftest.py](../tests/conftest.py) | `as_user` fixture (dependency override) + per-test in-memory AI cache |

### Frontend

| File | Holds |
| --- | --- |
| [frontend/src/lib/api.ts](../frontend/src/lib/api.ts) | `credentials: "include"`; `getCurrentUser`/`getProviders`/`loginUrl`/`logout`; 401 hook |
| [frontend/src/components/AuthProvider.tsx](../frontend/src/components/AuthProvider.tsx) | `useAuth()` — loads `/auth/me`, exposes `user`/`loading`/`signOut`/`refresh` |
| [frontend/src/components/AuthGuard.tsx](../frontend/src/components/AuthGuard.tsx) | redirects unauthenticated users to `/signin` |
| [frontend/src/components/AppShell.tsx](../frontend/src/components/AppShell.tsx) | nav + guarded content; `/signin` renders bare |
| [frontend/src/app/signin/page.tsx](../frontend/src/app/signin/page.tsx) | sign-in page with Google/Apple buttons + `?error=` handling |
| [frontend/src/components/BrandIcons.tsx](../frontend/src/components/BrandIcons.tsx) | Google/Apple SVG marks |
| [frontend/src/components/TopNav.tsx](../frontend/src/components/TopNav.tsx) | + user avatar/name and sign-out |

## How it works

### 1. Providers (Authlib, config-gated)

`services/oauth.py` registers an OIDC client per provider **only when its
credentials are set**, so the app runs with just Google configured (or none).
`enabled_providers()` drives both the sign-in buttons and a guard on the login
route. Apple doesn't use a static client secret — `_apple_client_secret()` mints
a short-lived ES256 JWT from the `.p8` key on each request.

### 2. Sign-in flow

1. `GET /auth/providers` → the frontend shows a button per enabled provider.
2. The button is a full-page link to `GET /auth/login/{provider}` → 302 to the
   provider's consent screen (Authlib stashes `state`/nonce in a server-signed
   session cookie via `SessionMiddleware`).
3. The provider redirects to `GET|POST /auth/callback/{provider}` (Apple uses
   `form_post`, hence both methods). Authlib validates the id-token; we read the
   verified `sub`/`email`/`name`.
4. `upsert_oauth_user` finds-or-creates the `User`: match by `(provider,
   subject)`, else by verified `email` (linking the identity), else create.
5. We set the **session JWT httpOnly cookie** and 302 to the frontend.

Any failure (denied consent, state mismatch, missing claims) redirects to
`/signin?error=…` — never a 500.

### 3. Session + `get_current_user`

`issue_session_token` signs `{sub: user_id, email, iat, exp}` (HS256,
`session_ttl_seconds`). `get_current_user` (in `deps.py`) reads the
`pulse_session` cookie, `decode_session_token` verifies signature + expiry, and
the user is loaded from the DB. Missing/'bad/expired' cookie → **401**
`{code: not_authenticated | invalid_session}`. Because every domain route already
depends on `CurrentUser`, swapping this one function switched the whole API from
the stub to real auth.

### 4. Per-user data isolation

Unchanged from earlier phases and now enforced against the *authenticated* user:
uploads stamp `Ticket.owner_id = user.id`; stats/tickets/insights filter every
query by `owner_id`/`user_id`; summaries key on `(user_id, week)`. Verified live:
user A's uploaded issue is invisible to user B's `/stats` and `/tickets`. (There
are no chat endpoints yet; the chat models will scope the same way when added.)

### 5. Frontend

`apiFetch` sends `credentials: "include"` so the cookie rides along, and routes a
`401` to a global handler. `AuthProvider` loads `/auth/me` once and shares
`user`; `AuthGuard` shows a spinner while loading and redirects to `/signin` when
signed out. `TopNav` shows the avatar/name and a sign-out button (`POST
/auth/logout` clears the cookie). The sign-in page reads `?error=` for friendly
messages on denied/failed auth.

## Per-function reference

### services/auth.py
- `AuthError` — raised for missing/bad/expired session tokens.
- `issue_session_token(user)` / `decode_session_token(token) -> UUID`.
- `set_session_cookie(response, user)` / `clear_session_cookie(response)`.
- `upsert_oauth_user(db, *, provider, subject, email, full_name) -> User`.

### services/oauth.py
- `get_oauth()` — cached Authlib `OAuth` registry (enabled providers only).
- `_apple_client_secret()` — ES256 JWT client secret for Apple.
- `enabled_providers() -> list[str]`.

### api/routes/auth.py
- `list_providers`, `login`, `callback`, `me`, `logout`; helpers `_redirect_uri`,
  `_frontend`, `_apple_name`.

### api/deps.py
- `get_current_user(db, session cookie) -> User`; `CurrentUser`, `DbSession`.

## Test it yourself (manual)

### Prereqs

Configure Google (see the README's provider-setup section) in `.env`:

```bash
PULSE_JWT_SECRET=<random>
PULSE_OAUTH_STATE_SECRET=<random>
PULSE_GOOGLE_CLIENT_ID=<...>.apps.googleusercontent.com
PULSE_GOOGLE_CLIENT_SECRET=<...>
```

Bring everything up:

```bash
cd /Users/bhavya/Desktop/PulseAI
conda activate pulseai
docker compose up -d
alembic upgrade head            # applies 0004
uvicorn app.main:app --reload --app-dir src     # :8000
cd frontend && npm run dev                        # :3000
```

### Sign in with Google

1. Open http://localhost:3000 → you're redirected to **/signin**.
2. Click **Continue with Google**, pick an account, grant consent.
3. You land back on the dashboard; the top-right shows your name + avatar.

### Confirm data isolation between two users

1. As user A: **Upload** a CSV, then **Analyse** a ticket. Note the Overview
   counts.
2. Sign out (top-right), sign in as **a different Google account** (user B).
3. User B's Overview/Tickets are **empty** — none of A's data is visible.
4. Sign back in as A → the data is there again.

### Sign out

Click the sign-out icon (top-right). The session cookie is cleared and you're
returned to **/signin**; hitting a protected route redirects there too.

### Automated

```bash
pytest -q                 # 125 passing (auth + isolation; DB tests auto-skip if down)
cd frontend && npm run build && npm run lint    # green, all routes static
```

## Graceful degradation
- Denied/failed OAuth → `/signin?error=…`, never a crash.
- No cookie / bad / expired → 401 with a typed code; the SPA redirects to sign-in.
- No providers configured → sign-in page explains what to set; login route 404s.
