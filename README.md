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

## Checks

```bash
ruff check . && ruff format --check .
mypy
pytest
```

See [docs/phase-0-foundations.md](docs/phase-0-foundations.md) for a full file/function reference.
