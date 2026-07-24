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

## Checks

```bash
ruff check . && ruff format --check .
mypy
pytest
```

See [docs/phase-0-foundations.md](docs/phase-0-foundations.md) for a full file/function reference.
