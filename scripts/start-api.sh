#!/usr/bin/env bash
# Start the FastAPI server in the background (no --reload — safe during
# evaluations). Kills any existing uvicorn on the same port first.
# Usage: ./scripts/start-api.sh
#
# Returns to the prompt once the server responds (or after 20s with an
# error + log tail if it didn't come up).

PORT="${API_PORT:-8001}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/.tmp"
LOG_FILE="$LOG_DIR/uvicorn.log"
PID_FILE="$LOG_DIR/uvicorn.pid"

mkdir -p "$LOG_DIR"

# 1. Kill any existing listener on $PORT
EXISTING=$(lsof -ti:"$PORT" 2>/dev/null || true)
if [ -n "$EXISTING" ]; then
  echo "[start-api] killing existing process on :$PORT (pid $EXISTING)"
  kill -9 $EXISTING 2>/dev/null || true
  sleep 1
fi

# 2. Truncate log so we only see this run
: > "$LOG_FILE"

cd "$ROOT"

# 3. Resolve python3 (use venv if present)
if [ -x "$ROOT/.venv/bin/python3" ]; then
  PY="$ROOT/.venv/bin/python3"
elif [ -x "$ROOT/venv/bin/python3" ]; then
  PY="$ROOT/venv/bin/python3"
else
  PY="$(command -v python3)"
fi

if [ -z "$PY" ]; then
  echo "[start-api] ERROR: python3 not found in PATH" >&2
  exit 1
fi

echo "[start-api] launching: $PY -m uvicorn web.api.main:app --host 127.0.0.1 --port $PORT"
echo "[start-api] log: $LOG_FILE"

# 4. Launch detached. setsid (Linux) or disown (mac) keeps it alive after
#    this shell exits.
nohup "$PY" -m uvicorn web.api.main:app \
  --host 127.0.0.1 --port "$PORT" \
  > "$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"
disown "$PID" 2>/dev/null || true
echo "[start-api] pid=$PID"

# 5. Wait up to 20s, but bail early if the process dies
for i in $(seq 1 20); do
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "[start-api] ERROR: uvicorn pid $PID died during startup" >&2
    echo "--- last 30 lines of $LOG_FILE ---" >&2
    tail -n 30 "$LOG_FILE" >&2
    exit 1
  fi
  if curl -fsS "http://localhost:$PORT/api/credentials/status" >/dev/null 2>&1; then
    echo "[start-api] ready on http://localhost:$PORT (pid $PID)"
    exit 0
  fi
  sleep 1
done

echo "[start-api] WARNING: server did not respond within 20s" >&2
echo "--- last 30 lines of $LOG_FILE ---" >&2
tail -n 30 "$LOG_FILE" >&2
exit 1
