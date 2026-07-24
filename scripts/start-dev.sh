#!/usr/bin/env bash
# Start the full PulseAI dev stack: FastAPI backend + Next.js frontend together.
#
# Runs both in the foreground and shuts both down cleanly on Ctrl-C. The backend
# is served with uvicorn --reload; the frontend with `npm run dev`. Infra
# (Postgres + Redis) is assumed to be up already — start it with:
#   docker compose up -d
#
# Usage:
#   ./scripts/start-dev.sh                 # backend :8000 + frontend :3000
#   BACKEND_PORT=8001 FRONTEND_PORT=3001 ./scripts/start-dev.sh
#   ./scripts/start-dev.sh --backend-only  # just the API
#   ./scripts/start-dev.sh --frontend-only # just the dashboard

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
case "${1:-}" in
  --backend-only) RUN_FRONTEND=false ;;
  --frontend-only) RUN_BACKEND=false ;;
  "") ;;
  *) echo "unknown option: $1" >&2; exit 2 ;;
esac

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
