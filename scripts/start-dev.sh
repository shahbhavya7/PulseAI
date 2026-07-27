#!/usr/bin/env bash
# Start the full PulseAI dev stack: FastAPI backend + Next.js frontend together.
#
# Brings up Postgres + Redis (via Docker Compose), waits for them to be
# healthy, runs pending migrations, then runs both apps in the foreground and
# shuts both down cleanly on Ctrl-C. The backend is served with
# uvicorn --reload; the frontend with `npm run dev`.
#
# Usage:
#   ./scripts/start-dev.sh                 # backend :8000 + frontend :3000
#   BACKEND_PORT=8001 FRONTEND_PORT=3001 ./scripts/start-dev.sh
#   ./scripts/start-dev.sh --backend-only  # just the API
#   ./scripts/start-dev.sh --frontend-only # just the dashboard
#   ./scripts/start-dev.sh --no-infra      # skip Docker/migrations (infra already up)

set -euo pipefail

# Monitor mode: each background job below becomes its own process-group leader,
# so we can signal the whole tree (uvicorn's reloader child, next-server, …) by
# its group id — a plain `kill <pid>` would orphan those grandchildren.
set -m

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

RUN_BACKEND=true
RUN_FRONTEND=true
RUN_INFRA=true
case "${1:-}" in
  --backend-only) RUN_FRONTEND=false ;;
  --frontend-only) RUN_BACKEND=false ;;
  --no-infra) RUN_INFRA=false ;;
  "") ;;
  *) echo "unknown option: $1" >&2; exit 2 ;;
esac

# --- Infra: Postgres + Redis, then migrations --------------------------------
# Skipped for --frontend-only (nothing backend needs a DB for) or --no-infra.
if $RUN_INFRA && $RUN_BACKEND; then
  echo "▶ infra    → starting Postgres + Redis (docker compose)"
  docker compose up -d postgres redis

  echo "⏳ waiting for Postgres + Redis to be healthy…"
  for _ in $(seq 1 60); do
    pg_status="$(docker inspect --format '{{.State.Health.Status}}' pulse-postgres 2>/dev/null || echo "starting")"
    redis_status="$(docker inspect --format '{{.State.Health.Status}}' pulse-redis 2>/dev/null || echo "starting")"
    if [[ "$pg_status" == "healthy" && "$redis_status" == "healthy" ]]; then
      break
    fi
    sleep 1
  done
  if [[ "$pg_status" != "healthy" || "$redis_status" != "healthy" ]]; then
    echo "postgres/redis did not become healthy in time (postgres=$pg_status redis=$redis_status)" >&2
    echo "check: docker compose logs postgres redis" >&2
    exit 1
  fi
  echo "✅ Postgres + Redis are healthy"

  echo "▶ migrations → alembic upgrade head"
  alembic upgrade head
fi

pids=()

# Kill each started job's whole process group on exit (Ctrl-C, error, or normal
# end). Signalling the negative pid targets the group, so reloader/worker and
# next-server children go down with it.
cleanup() {
  trap - INT TERM EXIT
  for pid in "${pids[@]:-}"; do
    [[ -n "$pid" ]] && kill -TERM "-$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

if $RUN_BACKEND; then
  echo "▶ backend  → http://localhost:${BACKEND_PORT}  (uvicorn --reload)"
  uvicorn app.main:app --reload --app-dir src --port "$BACKEND_PORT" &
  pids+=("$!")
fi

if $RUN_FRONTEND; then
  if [[ ! -d frontend/node_modules ]]; then
    echo "installing frontend deps (first run)…"
    (cd frontend && npm install)
  fi
  # Ensure the dashboard has its env file so it can find the API.
  if [[ ! -f frontend/.env.local ]]; then
    cp frontend/.env.local.example frontend/.env.local
    echo "created frontend/.env.local from example"
  fi
  echo "▶ frontend → http://localhost:${FRONTEND_PORT}  (next dev)"
  (cd frontend && exec npm run dev -- --port "$FRONTEND_PORT") &
  pids+=("$!")
fi

if [[ ${#pids[@]} -eq 0 ]]; then
  echo "nothing to start" >&2
  exit 0
fi

echo "(running — press Ctrl-C to stop)"

# Block until any job exits, then cleanup() (via the trap) tears down the rest.
# `wait -n` isn't in macOS bash 3.2, so poll the pids and keep `wait`-ing so the
# INT/TERM trap fires promptly.
while :; do
  for pid in "${pids[@]}"; do
    kill -0 "$pid" 2>/dev/null || exit 0
  done
  wait -n 2>/dev/null || sleep 1
done
