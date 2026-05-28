#!/usr/bin/env bash
# One-command Google OAuth re-auth + API restart.
#
# When the weekly OAuth token expires (sensitive scopes on an unverified
# production app are capped at 7 days by Google), the API server starts
# returning 500s on every Classroom/Drive/Gmail call. This script:
#   1. Stops the running uvicorn (port 8001) cleanly.
#   2. Archives the dead token.json so we can compare later if needed.
#   3. Runs setup_drive.py — opens a browser, you consent, fresh token.json is saved.
#   4. Restarts uvicorn in the background, log -> .tmp/uvicorn.log.
#
# Usage:  ./scripts/reauth.sh
#
# After this script returns OK, hard-refresh the queue page; the
# /api/credentials/status banner should clear within ~30 seconds.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

PORT="${API_PORT:-8001}"
LOG="$PROJECT_ROOT/.tmp/uvicorn.log"

say() { printf '\033[1;36m▸ %s\033[0m\n' "$*"; }
ok()  { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
err() { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; }

# 1. Stop uvicorn (port-bound, for safety)
say "Stopping uvicorn on :$PORT"
if PIDS=$(lsof -ti ":$PORT" 2>/dev/null); then
  echo "$PIDS" | xargs kill -9 2>/dev/null || true
  ok "killed pids: $PIDS"
else
  ok "nothing listening on :$PORT"
fi

# 2. Archive existing token
if [[ -f token.json ]]; then
  ts=$(date +%Y%m%d-%H%M%S)
  mv token.json "token.json.expired-$ts"
  ok "archived token.json -> token.json.expired-$ts"
else
  ok "no token.json present"
fi

# 3. Re-auth via OAuth flow (opens browser)
say "Launching OAuth flow — consent in the browser tab that opens"
python3 tools/setup_drive.py

if [[ ! -f token.json ]]; then
  err "token.json was not written — setup_drive.py did not complete"
  exit 1
fi
ok "fresh token.json saved"

# 4. Restart API server in background
mkdir -p "$(dirname "$LOG")"
say "Restarting uvicorn on :$PORT (log: $LOG)"
nohup python3 -m uvicorn web.api.main:app \
  --host 127.0.0.1 --port "$PORT" \
  >"$LOG" 2>&1 &
NEW_PID=$!
disown "$NEW_PID" 2>/dev/null || true

# Wait for the port to come up
for i in $(seq 1 15); do
  if curl -s -m 2 "http://127.0.0.1:$PORT/api/credentials/status" -o /dev/null -w '%{http_code}' 2>/dev/null | grep -q 200; then
    ok "uvicorn pid $NEW_PID listening on :$PORT"
    say "Done. Hard-refresh the web console."
    exit 0
  fi
  sleep 1
done

err "uvicorn did not come up within 15s — check $LOG"
exit 1
