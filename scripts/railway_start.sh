#!/bin/sh
set -e

cd "$(dirname "$0")/.." 2>/dev/null || cd /app 2>/dev/null || true

mkdir -p eval1/outputs eval1/data/uploads

PORT="${PORT:-8000}"
PY="$(command -v python3 2>/dev/null || command -v python 2>/dev/null || echo python3)"
echo "[start] Eval1 on 0.0.0.0:${PORT} via ${PY} (cwd=$(pwd))"

exec "$PY" -m uvicorn eval1.main:app --host 0.0.0.0 --port "${PORT}"
