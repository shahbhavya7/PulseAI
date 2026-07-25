# PulseAI

A production-quality customer-ticket triage system: a **FastAPI** backend that
classifies tickets with an LLM (grounded, structured output), aggregates weekly
insight, and answers questions over the data via a grounded chat — plus a
**Next.js** dashboard. **Issue** is the atomic unit: a ticket has many issues.

- FastAPI · sync SQLAlchemy 2.0 + Alembic · PostgreSQL (pgvector) + Redis
- OpenAI structured outputs + embeddings; hybrid (SQL + vector) retrieval
- Google/Apple OIDC **and** email/password auth; per-user data isolation
- Next.js (App Router) + Tailwind + Recharts dashboard
- ruff + mypy(strict) + pytest; graceful degradation on every external call

## Cold start (clone → running in ~5 minutes)

**Prereqs:** Docker, Python 3.12 (conda or venv), Node 20+. That's it.

```bash
# 1. Config — copy the template; the defaults boot everything locally.
cp .env.example .env

# 2. Infra — Postgres (pgvector) + Redis.
docker compose up -d

# 3. Backend deps + schema.
conda create -y -n pulseai python=3.12 && conda activate pulseai   # or: python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head                # enables pgvector, creates tables, seeds dev-user password

# 4. Run backend + dashboard together (Ctrl-C stops both).
./scripts/start-dev.sh              # backend :8000 + frontend :3000 (installs frontend deps on first run)
```

Open **http://localhost:3000**, sign in with **`dev@pulseai.local` / `pulseai-dev`**
(email sign-in works with zero OAuth setup), and you're on the dashboard.

Backend only: `uvicorn app.main:app --reload --app-dir src`, then check
http://localhost:8000/health and http://localhost:8000/ready.

> **AI features** (classification, weekly summaries, chat) need
> `PULSE_OPENAI_API_KEY` in `.env`. Without it the app still runs end-to-end —
> upload/browse/auth work, and AI calls degrade to a clean 503 instead of
> crashing. See **Graceful degradation** below.

## Docs

| Doc | What |
| --- | --- |
| [docs/phase-0-foundations.md](docs/phase-0-foundations.md) | scaffold, models, config, health |
| [docs/phase-1-ingestion.md](docs/phase-1-ingestion.md) | upload → parse/clean/redact/dedupe |
| [docs/phase-2-ai-pipeline.md](docs/phase-2-ai-pipeline.md) | LLM classification (structured, few-shot) |
| [docs/phase-3-insights.md](docs/phase-3-insights.md) | embeddings, themes, weekly summary, stats |
| [docs/phase-4-dashboard.md](docs/phase-4-dashboard.md) | Next.js dashboard |
| [docs/phase-5-auth.md](docs/phase-5-auth.md) | Google/Apple OIDC + email/password |
| [docs/phase-6-chat.md](docs/phase-6-chat.md) | hybrid retrieval chat + cross-session memory |
| [docs/phase-7-hardening.md](docs/phase-7-hardening.md) | failure hardening + evidence |
| [docs/accuracy.md](docs/accuracy.md) | classifier accuracy on a blind labelled set |
| [DEMO.md](DEMO.md) | mentor click-path mapped to the rubric |

## Graceful degradation

Every external call fails soft, never crashing the request:

- **OpenAI down / no key** → analysis + summaries return **503 `ai_unavailable`**;
  chat streams a friendly "assistant unavailable" message; embeddings are skipped
  (issues kept, flagged `needs_reembed`).
- **Redis down** → the AI cache silently misses (best-effort); requests still work.
- **Database down** → `/ready` reports **503** with the per-dependency breakdown
  (never raises); a domain request hitting a DB error returns a clean **503
  `database_unavailable`** via the global handler, not a leaked 500.

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

### Email + password (no OAuth setup needed)

Email sign-in is on by default (`PULSE_EMAIL_LOGIN_ENABLED=true`), so you can use
the app without configuring Google/Apple: create an account from the **/signin**
page, or sign in to the **existing local data** with the seeded dev user —

```
email:    dev@pulseai.local
password: pulseai-dev          # PULSE_DEV_PASSWORD; set by migration 0005
```

(Set `PULSE_EMAIL_LOGIN_ENABLED=false` to force OAuth-only.)

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
