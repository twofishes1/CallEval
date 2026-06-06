#!/bin/sh
set -e

cd "$(dirname "$0")/.." 2>/dev/null || cd /app 2>/dev/null || true

mkdir -p eval1/outputs eval1/data/uploads

PORT="${PORT:-8000}"
echo "[start] Eval1 listening on 0.0.0.0:${PORT} (cwd=$(pwd))"

exec python -m uvicorn eval1.main:app --host 0.0.0.0 --port "${PORT}"
