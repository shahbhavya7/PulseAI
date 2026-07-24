# Phase 5 — Authentication (Google / Apple OIDC + email/password)

Replaces the Phase 1 dev-user stub (`X-User-Id` header) with **real sign-in**:
Google and Apple (OpenID Connect) **and** email + password. After a successful
login the backend issues a signed **session JWT in an httpOnly cookie**; every
route resolves the acting user from that cookie and scopes all data to them.

Email sign-in exists so the app is usable with zero OAuth setup, and so the
existing local data (owned by the legacy `dev@pulseai.local` user) stays
reachable — migration 0005 gives that user a password (`PULSE_DEV_PASSWORD`,
default `pulseai-dev`), so signing in with those credentials lands on all the
current tickets/summaries.

## Where things live

### Backend

| File | Holds |
| --- | --- |
| [src/app/core/config.py](../src/app/core/config.py) | auth settings: `jwt_secret`, cookie flags, base URLs, Google/Apple creds, `email_login_enabled`; `google_enabled`/`apple_enabled` |
| [src/app/models/user.py](../src/app/models/user.py) | `oauth_provider` + `oauth_subject` + `password_hash` columns; unique `(provider, subject)` |
| [alembic/versions/0004_user_oauth_identity.py](../alembic/versions/0004_user_oauth_identity.py) | OAuth-identity migration |
| [alembic/versions/0005_user_password_hash.py](../alembic/versions/0005_user_password_hash.py) | `password_hash` column + sets the dev user's password |
| [src/app/services/auth.py](../src/app/services/auth.py) | session JWTs, cookie set/clear, `upsert_oauth_user`, `hash_password`/`verify_password`, `register_user`/`authenticate_user` |
| [src/app/services/oauth.py](../src/app/services/oauth.py) | Authlib registry; Google + Apple (config-gated); Apple client-secret JWT |
| [src/app/api/routes/auth.py](../src/app/api/routes/auth.py) | `/auth/providers`, `/auth/register`, `/auth/login/email`, `/auth/login/{p}`, `/auth/callback/{p}`, `/auth/me`, `/auth/logout` |
| [src/app/api/deps.py](../src/app/api/deps.py) | `get_current_user` — reads the session cookie → `User` (401 otherwise) |
| [src/app/schemas/auth.py](../src/app/schemas/auth.py) | `CurrentUserResponse`, `ProvidersResponse`, `RegisterRequest`, `LoginRequest` |
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

### 2b. Email + password sign-in

Enabled by default (`email_login_enabled`); `GET /auth/providers` reports it via
`{"email": true}` so the sign-in page can show the form.

- `POST /auth/register` `{email, password, full_name?}` — `register_user` hashes
  the password with **bcrypt** (`hash_password`), rejects a weak password
  (schema enforces ≥8 chars → 422) or a duplicate email (`email_taken` → 409),
  creates the user, then sets the session cookie and returns the user (201).
- `POST /auth/login/email` `{email, password}` — `authenticate_user` looks up the
  email and checks the hash with `verify_password`. Unknown email, no password
  set (OAuth-only account), or a wrong password all raise the **same**
  `invalid_credentials` → **401**, so login never reveals which emails exist.
  Success sets the session cookie and returns the user (200).

Both mint the same session JWT cookie as the OAuth flow, so everything
downstream (`get_current_user`, isolation) is identical regardless of how you
signed in. When `email_login_enabled` is false, both routes 404.

**Reaching the existing data:** migration 0005 sets a password on
`dev@pulseai.local` (the legacy owner of the current local tickets). Sign in
with that email + `PULSE_DEV_PASSWORD` (default `pulseai-dev`) to land on it.

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
/auth/logout` clears the cookie). The sign-in page offers the **email/password
form** (with a login ↔ create-account toggle) plus any OAuth buttons; on success
it calls `refresh()` so the guard forwards to the dashboard. It reads `?error=`
for friendly messages on denied/failed OAuth. `loginEmail`/`registerEmail` post
JSON and rely on the cookie the backend sets.

## Per-function reference

### services/auth.py
- `AuthError` — missing/bad/expired session token. `CredentialsError(code,
  message)` — bad email/password or registration conflict.
- `issue_session_token(user)` / `decode_session_token(token) -> UUID`.
- `set_session_cookie(response, user)` / `clear_session_cookie(response)`.
- `upsert_oauth_user(db, *, provider, subject, email, full_name) -> User`.
- `hash_password(pw)` / `verify_password(pw, hash)` — bcrypt.
- `register_user(db, *, email, password, full_name) -> User` — weak-password /
  duplicate-email guards.
- `authenticate_user(db, *, email, password) -> User` — uniform
  `invalid_credentials` on any failure.

### services/oauth.py
- `get_oauth()` — cached Authlib `OAuth` registry (enabled providers only).
- `_apple_client_secret()` — ES256 JWT client secret for Apple.
- `enabled_providers() -> list[str]`.

### api/routes/auth.py
- `list_providers`, `register`, `login_email`, `login`, `callback`, `me`,
  `logout`; helpers `_redirect_uri`, `_frontend`, `_apple_name`,
  `_session_response`.

### api/deps.py
- `get_current_user(db, session cookie) -> User`; `CurrentUser`, `DbSession`.

## Test it yourself (manual)

### Prereqs

Email sign-in needs **no OAuth setup** — just the session secrets (a dev default
exists, but set real ones for anything shared). Google is optional (README's
provider-setup section). Bring everything up:

```bash
cd /Users/bhavya/Desktop/PulseAI
conda activate pulseai
docker compose up -d
alembic upgrade head            # applies 0004 + 0005 (dev-user password)
uvicorn app.main:app --reload --app-dir src     # :8000
cd frontend && npm run dev                        # :3000
```

### Sign in with email (and reach the existing data)

1. Open http://localhost:3000 → you're redirected to **/signin**.
2. Enter **dev@pulseai.local** / **pulseai-dev** → **Sign in**.
3. You land on the dashboard showing the **existing tickets/summaries** (the dev
   user owns them). Top-right shows the account + sign-out.

Or create a fresh account: toggle **Create an account**, enter an email +
password (≥8 chars) → you're signed in to an empty, isolated workspace.

### Sign in with Google (optional)

With Google configured, the **Continue with Google** button appears below the
email form. Click it, grant consent, and you land back on the dashboard.

### Confirm data isolation between two users

1. Sign in as **dev@pulseai.local** — note the Overview counts (existing data).
2. Sign out (top-right), **create a new account** (or use a second Google login).
3. The new user's Overview/Tickets are **empty** — none of the dev data shows.
4. Sign back in as the dev user → the data is there again.

### Sign out

Click the sign-out icon (top-right). The session cookie is cleared and you're
returned to **/signin**; hitting a protected route redirects there too.

### Automated

```bash
pytest -q                 # 131 passing (OAuth + email + isolation; DB tests auto-skip if down)
cd frontend && npm run build && npm run lint    # green, all routes static
```

## Graceful degradation
- Denied/failed OAuth → `/signin?error=…`, never a crash.
- Bad email/password → uniform 401 `invalid_credentials` (no email enumeration).
- Duplicate registration → 409; weak password → 422.
- No cookie / bad / expired → 401 with a typed code; the SPA redirects to sign-in.
- `email_login_enabled=false` → register/login-email 404; only OAuth remains.
- No providers configured → sign-in page explains what to set; login route 404s.
