# PulseAI — single image that serves both the FastAPI backend and the Next.js
# dashboard. Multi-stage: build the frontend, install the backend, then copy
# only what the runtime needs into a slim final image.
#
#   Build:  docker build -t pulseai .
#   Run:    docker run --rm -p 3000:3000 -p 8000:8000 --env-file .env pulseai
#
# Ports: dashboard 3000, API 8000. On boot it waits for Postgres, runs
# `alembic upgrade head`, then starts uvicorn + the Next server together.

# ---------------------------------------------------------------------------
# Stage 1 — build the Next.js dashboard (standalone output)
# ---------------------------------------------------------------------------
FROM node:20-bookworm-slim AS frontend-build
WORKDIR /app/frontend

# Install deps against the lockfile for reproducible builds.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

# Build. The dashboard is a static client that talks to the API at this base
# URL; it's a build-time public var, overridable at build with --build-arg.
COPY frontend/ ./
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 — install the Python backend into a venv
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS backend-build
WORKDIR /app

# Build tools for psycopg/pgvector wheels; removed from the final image.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# A dedicated venv keeps the runtime image clean and copyable.
ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install the project. Copy the metadata + source, then `pip install .` so the
# `app` package is importable as `app.*` (src layout, see pyproject).
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

# ---------------------------------------------------------------------------
# Stage 3 — the runtime image (Node + Python side by side)
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app

# Node runtime for the Next standalone server, plus a Postgres client so the
# entrypoint can wait for the DB. postgresql-client gives us `pg_isready`.
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates gnupg postgresql-client \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
       | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
       > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Backend venv + source + migrations.
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
COPY --from=backend-build /opt/venv /opt/venv
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini

# Frontend: the standalone server bundle (server.js lands at frontend/server.js)
# plus the hashed static assets it serves. This project has no public/ dir.
COPY --from=frontend-build /app/frontend/.next/standalone ./frontend/
COPY --from=frontend-build /app/frontend/.next/static ./frontend/.next/static

# Entrypoint: wait for DB, migrate, start both servers.
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Run as a non-root user.
RUN useradd --create-home --uid 10001 pulse && chown -R pulse:pulse /app
USER pulse

# The backend imports `app.*` from src; alembic and uvicorn both need it.
ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    BACKEND_PORT=8000 \
    FRONTEND_PORT=3000 \
    HOSTNAME=0.0.0.0

EXPOSE 8000 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
  CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
