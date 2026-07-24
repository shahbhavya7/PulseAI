# PulseAI Backend

Production-quality FastAPI backend. **Issue** is the atomic unit: a ticket has many issues.

- Sync SQLAlchemy 2.0 + Alembic
- `StrEnum` values stored as `String` columns
- pydantic-settings + `.env` (no hardcoded secrets)
- PostgreSQL (pgvector image) + Redis
- ruff + mypy + pytest

## Quick start

```bash
cp .env.example .env
docker compose up -d                       # Postgres (pgvector) + Redis
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head                       # enables pgvector + creates tables
uvicorn app.main:app --reload --app-dir src
```

Then hit http://localhost:8000/health and http://localhost:8000/ready.

### Start everything (backend + dashboard)

To run the FastAPI backend **and** the Next.js dashboard together (Ctrl-C stops
both), use the dev start script — it installs frontend deps and creates
`frontend/.env.local` on first run:

```bash
docker compose up -d                       # Postgres + Redis first
./scripts/start-dev.sh                      # backend :8000 + frontend :3000
```

```bash
./scripts/start-dev.sh --backend-only       # just the API
./scripts/start-dev.sh --frontend-only      # just the dashboard
BACKEND_PORT=8001 FRONTEND_PORT=3001 ./scripts/start-dev.sh
```

Then open http://localhost:3000. See [docs/phase-4-dashboard.md](docs/phase-4-dashboard.md).

## Authentication (Google / Apple sign-in)

Sign-in uses OIDC; after login the backend sets a signed **httpOnly session
cookie**. Set the secrets in `.env` (never commit them). See
[docs/phase-5-auth.md](docs/phase-5-auth.md) for the full design.

First, generate the session secrets:

```bash
python -c "import secrets; print('PULSE_JWT_SECRET=' + secrets.token_urlsafe(48))"
python -c "import secrets; print('PULSE_OAUTH_STATE_SECRET=' + secrets.token_urlsafe(48))"
```

### Google setup

1. [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services
   → Credentials → Create credentials → OAuth client ID**.
2. Application type **Web application**.
3. **Authorized redirect URI** (must match exactly):
   `http://localhost:8000/api/auth/callback/google`
4. Copy the client id/secret into `.env`:
   ```bash
   PULSE_GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
   PULSE_GOOGLE_CLIENT_SECRET=xxxxx
   ```

Restart the backend — the **Continue with Google** button now appears at
`/signin`.

### Apple setup (optional; needs a paid Apple Developer account)

Apple is wired end-to-end but only activates when all four vars are set:

1. Apple Developer → **Certificates, IDs & Profiles**:
   - a **Services ID** (this is the `client_id`, e.g. `com.yourorg.pulseai.web`),
   - a **Sign in with Apple key** (`.p8`) — note its **Key ID** and your **Team ID**.
2. Add the return URL: `http://localhost:8000/api/auth/callback/apple` (Apple
   requires HTTPS in production).
3. Put the values in `.env` (the private key is the `.p8` file contents):
   ```bash
   PULSE_APPLE_CLIENT_ID=com.yourorg.pulseai.web
   PULSE_APPLE_TEAM_ID=XXXXXXXXXX
   PULSE_APPLE_KEY_ID=XXXXXXXXXX
   PULSE_APPLE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
   ```

### Redirect-URI summary

| Provider | Authorized redirect URI (local) |
| --- | --- |
| Google | `http://localhost:8000/api/auth/callback/google` |
| Apple  | `http://localhost:8000/api/auth/callback/apple`  |

In production, replace the host with your API domain and set
`PULSE_BACKEND_BASE_URL`, `PULSE_FRONTEND_BASE_URL`, and
`PULSE_SESSION_COOKIE_SECURE=true`.

## Checks

```bash
ruff check . && ruff format --check .
mypy
pytest
```

See [docs/phase-0-foundations.md](docs/phase-0-foundations.md) for a full file/function reference.
