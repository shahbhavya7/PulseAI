#!/usr/bin/env bash
# Container entrypoint: wait for Postgres, run migrations, then serve the API
# and the dashboard together. Either process exiting brings the container down.
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

# --- Wait for Postgres --------------------------------------------------------
# Prefer explicit host/port; otherwise parse them out of a full DATABASE_URL.
PG_HOST="${PULSE_POSTGRES_HOST:-}"
PG_PORT="${PULSE_POSTGRES_PORT:-5432}"
if [[ -z "$PG_HOST" && -n "${PULSE_DATABASE_URL:-}" ]]; then
  # postgresql+psycopg://user:pass@HOST:PORT/db  ->  HOST / PORT
  hostport="${PULSE_DATABASE_URL#*@}"; hostport="${hostport%%/*}"
  PG_HOST="${hostport%%:*}"
  [[ "$hostport" == *:* ]] && PG_PORT="${hostport##*:}"
fi
PG_HOST="${PG_HOST:-postgres}"

echo "⏳ waiting for Postgres at ${PG_HOST}:${PG_PORT} …"
for _ in $(seq 1 60); do
  if pg_isready -h "$PG_HOST" -p "$PG_PORT" >/dev/null 2>&1; then
    echo "✅ Postgres is ready"
    break
  fi
  sleep 1
done

# --- Migrate ------------------------------------------------------------------
echo "▶ running database migrations (alembic upgrade head)"
alembic upgrade head

# --- Start both servers -------------------------------------------------------
pids=()
cleanup() {
  trap - INT TERM EXIT
  for pid in "${pids[@]:-}"; do kill -TERM "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "▶ backend  → :${BACKEND_PORT}"
uvicorn app.main:app --app-dir src --host 0.0.0.0 --port "$BACKEND_PORT" &
pids+=("$!")

echo "▶ frontend → :${FRONTEND_PORT}"
# The Next standalone bundle is a server.js at frontend/server.js.
PORT="$FRONTEND_PORT" HOSTNAME=0.0.0.0 node frontend/server.js &
pids+=("$!")

echo "🚀 PulseAI is up — dashboard on :${FRONTEND_PORT}, API on :${BACKEND_PORT}"

# Exit as soon as either server stops, so Docker restarts a crashed container.
while :; do
  for pid in "${pids[@]}"; do
    kill -0 "$pid" 2>/dev/null || exit 0
  done
  sleep 2
done
