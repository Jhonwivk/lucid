#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_PID=""
WEB_PID=""

cleanup() {
  if [[ -n "${WEB_PID}" ]] && kill -0 "${WEB_PID}" 2>/dev/null; then
    kill "${WEB_PID}" 2>/dev/null || true
  fi
  if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" 2>/dev/null; then
    kill "${API_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

cd "${ROOT}/api"
# shellcheck disable=SC1091
source .venv/bin/activate
uvicorn app.main:app --app-dir . --host 127.0.0.1 --port 8000 --reload &
API_PID=$!

cd "${ROOT}/web"
npm run dev -- --host 127.0.0.1 --port 5173 &
WEB_PID=$!

echo "LUCID API: http://127.0.0.1:8000/api/health"
echo "LUCID Web: http://127.0.0.1:5173/"
wait
