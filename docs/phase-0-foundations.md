# Phase 0 — Foundations

This document is the reference for the PulseAI backend scaffold: the layout, every
file, and every public function/class, plus how to run and verify it.

## Locked decisions (and where they live)

| Decision | Realized in |
| --- | --- |
| **Issue is the atomic unit** (ticket → many issues) | [src/app/models/issue.py](../src/app/models/issue.py), FK + relationship in [ticket.py](../src/app/models/ticket.py) |
| **Sync SQLAlchemy 2.0 + Alembic** | [src/app/db/](../src/app/db/), [alembic/](../alembic/) |
| **`StrEnum` values stored as `String` columns** | [src/app/models/enums.py](../src/app/models/enums.py) + every `mapped_column(String(32), ...)` |
| **pydantic-settings + `.env`, no hardcoded secrets** | [src/app/core/config.py](../src/app/core/config.py), [.env.example](../.env.example) |
| **PostgreSQL (pgvector image) + Redis** | [docker-compose.yml](../docker-compose.yml) |
| **ruff + mypy + pytest** | [pyproject.toml](../pyproject.toml) |

## Directory layout

```
PulseAI/
├── pyproject.toml            # deps, ruff, mypy (strict), pytest config
├── .env.example              # every setting; copy to .env (never committed)
├── .gitignore
├── docker-compose.yml        # Postgres (pgvector) + Redis
├── alembic.ini               # Alembic config; DSN injected at runtime
├── alembic/
│   ├── env.py                # pulls DSN + metadata from the app
│   ├── script.py.mako        # migration template
│   └── versions/
│       └── 0001_initial.py   # enable pgvector + create all tables
├── src/app/
│   ├── __init__.py           # __version__
│   ├── main.py               # app factory + ASGI entrypoint
│   ├── core/                 # config, logging, redis
│   ├── db/                   # Base, mixin, engine/session, get_db
│   ├── models/               # enums + six ORM models
│   ├── schemas/              # pydantic API models
│   ├── services/             # business logic (health service)
│   └── api/routes/           # health + ready endpoints
├── tests/                    # conftest + health tests
└── docs/phase-0-foundations.md
```

## File-by-file reference

### Project root

- **pyproject.toml** — `src`-layout packaging (hatchling, `packages = ["src/app"]`).
  Runtime deps (FastAPI, SQLAlchemy 2.0, Alembic, psycopg 3, pgvector, redis,
  pydantic, pydantic-settings) and a `dev` extra (ruff, mypy, pytest, httpx).
  ruff lint rule-set (`E,F,I,N,UP,B,C4,SIM,TID`), **mypy `strict = true`**, and
  pytest configured with `pythonpath = ["src"]`.
- **.env.example** — documents every `PULSE_`-prefixed setting. No real secrets;
  copy to `.env` for local dev.
- **.gitignore** — ignores `.env` (keeps `.env.example`), caches, build output.
- **docker-compose.yml** — two services with healthchecks:
  `postgres` (`pgvector/pgvector:pg16`) and `redis` (`redis:7-alpine`).
  Credentials/port read from `.env` with local-dev fallbacks; named volumes
  persist data.

### `src/app/__init__.py`
- `__version__` — single source of the app version, surfaced by `/health`.

### `src/app/core/` — cross-cutting concerns

**config.py**
- `Environment(StrEnum)` — `LOCAL / TEST / STAGING / PRODUCTION`.
- `Settings(BaseSettings)` — typed config, `env_prefix="PULSE_"`, reads `.env`.
  Fields: app (`env`, `debug`, `log_level`, `api_prefix`, `project_name`),
  Postgres (`database_url` **or** the `postgres_*` parts), `redis_url`, and
  engine tuning (`db_pool_size`, `db_max_overflow`, `db_pool_pre_ping`).
  - `_assemble_database_url()` — `model_validator` that builds `database_url`
    from the parts when a full DSN wasn't supplied.
  - `sqlalchemy_url` — computed str DSN for SQLAlchemy/Alembic.
  - `is_production` — computed bool.
- `get_settings()` — `lru_cache`d accessor; parses env/`.env` once per process.

**logging.py**
- `configure_logging(level="INFO")` — idempotent root-logger setup (stdout,
  consistent format); tames `uvicorn.access`.
- `get_logger(name)` — thin `logging.getLogger` wrapper for import consistency.

**redis.py**
- `get_redis()` — `lru_cache`d `redis.Redis` client (`decode_responses=True`,
  short socket timeouts).
- `ping_redis()` — returns `bool`, never raises; used by readiness.

### `src/app/db/` — database layer

**base.py**
- `NAMING_CONVENTION` — deterministic constraint/index names for stable Alembic output.
- `Base(DeclarativeBase)` — declarative root; carries the naming convention.
- `TimestampMixin` — server-managed `created_at` / `updated_at` (`timezone=True`,
  `server_default=now()`, `onupdate=now()`).

**session.py**
- `get_engine()` — `lru_cache`d `Engine` (pool sizing + `pool_pre_ping` from settings).
- `get_sessionmaker()` — `lru_cache`d `sessionmaker` (`autoflush=False`,
  `expire_on_commit=False`).
- `get_db()` — FastAPI dependency; yields a request-scoped `Session`, rolls back
  on exception, always closes. Commits are the caller's responsibility.
- `ping_db()` — runs `SELECT 1`; returns `bool`, never raises; used by readiness.

### `src/app/models/` — ORM models

**enums.py** — all `StrEnum`; `.value` is what lands in the `String` column:
`UserRole`, `TicketSource`, `TicketStatus`, `TicketPriority`, `IssueSeverity`,
`IssueStatus`, `IssueCategory`, `SummaryStatus`, `ChatSessionStatus`, `ChatRole`.

**user.py — `User`** (`users`): `id` (UUID pk), unique indexed `email`,
`full_name`, `role`, `is_active`; relationships to `tickets` and `chat_sessions`
(cascade delete-orphan).

**ticket.py — `Ticket`** (`tickets`): the container. `owner_id` → `users`,
`title`, `body`, `source`, `status` (indexed), `priority`, `external_id`
(indexed, for provider dedupe); `owner` + ordered `issues` relationships.

**issue.py — `Issue`** (`issues`): **the atomic unit.** `ticket_id` → `tickets`,
`title`, `description`, `category`, `severity`, `status`. Triage metadata:
`confidence` (float, `CheckConstraint 0..1`), `needs_manual_review` (bool),
`flags` (`JSONB` list), `content_hash` (indexed), `week` (`YYYY-Www`, indexed),
and `embedding` (`Vector(1536)` from pgvector). Constraints/indexes:
`UniqueConstraint(ticket_id, content_hash)`, composite `(week, status)` index,
`needs_manual_review` index.
- `EMBEDDING_DIM = 1536` — shared with the migration.
- `Issue.metadata_summary` — property returning compact triage dict.

**weekly_summary.py — `WeeklySummary`** (`weekly_summaries`): one row per ISO
`week` (unique). `status`, `content`, `issue_count`, `stats` (`JSONB`).

**chat_session.py — `ChatSession`** (`chat_sessions`): `user_id` → `users`,
`title`, `status` (indexed); ordered `messages` relationship.

**chat_message.py — `ChatMessage`** (`chat_messages`): `session_id` →
`chat_sessions`, `role`, `content`, `token_count`, `extra` (`JSONB`).

`models/__init__.py` re-exports every model + enum so importing the package
fully populates `Base.metadata` (required by Alembic autogenerate).

### `src/app/schemas/` — API models
- **base.py — `APIModel`**: `from_attributes=True` (build from ORM),
  `extra="forbid"` (reject unknown input fields).
- **health.py**: `HealthResponse` (status/service/version), `DependencyStatus`
  (name/ok), `ReadinessResponse` (ready + dependency list).

### `src/app/services/` — business logic
- **health.py — `HealthService`**: `liveness()` builds the `HealthResponse`
  without touching dependencies; `readiness()` probes DB + Redis (non-raising)
  and returns `ReadinessResponse` with `ready = all deps ok`.

### `src/app/api/routes/` — HTTP layer
- **routes/__init__.py** — `api_router` aggregating all route modules.
- **health.py**:
  - `GET /health` → 200 liveness whenever the process is up.
  - `GET /ready` → 200 when all deps healthy, else **503** with the
    per-dependency breakdown. Failures degrade the status code; they never raise.

### `src/app/main.py`
- `lifespan(app)` — configures logging on startup, logs start/stop.
- `create_app()` — builds the `FastAPI` app, mounts `api_router` at root and
  under `settings.api_prefix`.
- `app` — module-level ASGI instance for `uvicorn app.main:app`.

### `alembic/`
- **env.py** — imports `Base` and the models package, injects
  `settings.sqlalchemy_url` at runtime (no DSN in `alembic.ini`), supports
  offline + online modes, `compare_type=True`.
- **versions/0001_initial.py** — `upgrade()` runs
  `CREATE EXTENSION IF NOT EXISTS vector` **before** creating the `Vector`
  column, then creates all six tables with their indexes/constraints;
  `downgrade()` drops tables in FK-safe order and drops the extension.

### `tests/`
- **conftest.py** — forces `PULSE_ENV=test` before app import; `client` fixture
  yields a `TestClient` with lifespan run.
- **test_health.py** — `/health` returns 200 + identity; `/ready` returns 200
  when deps mocked up; `/ready` returns **503** (no crash) when a dep is down.

## Run & verify

### 1. Infrastructure
```bash
cp .env.example .env
docker compose up -d          # Postgres (pgvector) + Redis, both healthchecked
```
> If host port 5432 is already taken, set `PULSE_POSTGRES_PORT=5433` in `.env`
> (the compose mapping and the app both read it) and re-run `docker compose up -d`.

### 2. Environment (fresh conda env)
```bash
conda create -y -n pulseai python=3.12
conda activate pulseai
pip install -e ".[dev]"
```

### 3. Migrate
```bash
alembic upgrade head          # enables pgvector + creates all tables
alembic current               # -> 0001_initial (head)
```

### 4. Static checks + tests
```bash
ruff check . && ruff format --check .
mypy                          # strict; 25 source files
pytest                        # 3 passed
```

### 5. Run the app
```bash
uvicorn app.main:app --reload --app-dir src
curl -s localhost:8000/health   # {"status":"ok",...}           HTTP 200
curl -s localhost:8000/ready    # {"ready":true,"dependencies":[...]} HTTP 200
```

### Verified in this scaffold
- `ruff` clean, `ruff format` clean, **`mypy` strict: no issues in 25 files**,
  **`pytest`: 3 passed**.
- `alembic upgrade head` created all 7 relations (6 tables + `alembic_version`)
  and enabled the `vector` extension against `pgvector/pgvector:pg16`.
- Live `/health` → 200; `/ready` → 200 with deps up; `/ready` → **503**
  (degraded, no crash) after stopping Redis.

## What Phase 0 intentionally defers
Domain endpoints (ticket/issue CRUD, triage, weekly summarization, chat) and
their services/schemas. The models, migration, session management, and app
wiring are in place so those land as additive routers + services + migrations.
```
