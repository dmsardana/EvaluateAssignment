# OPERATIONS — Start, Stop, Wake

Day-to-day commands for running the EvaluateAssignment stack on a dev MacBook. For what the system does, see [RUNBOOK.md](RUNBOOK.md). For one-time setup (credentials, Google OAuth, env vars), see [workflows/setup.md](workflows/setup.md).

---

## The four services

| # | Service | What it does | Where it runs |
|---|---|---|---|
| 1 | **Postgres** (Docker) | Source of truth for `scores`, `students`, `answer_key_state`. | `evalassign-db` container on host port **5433**. |
| 2 | **FastAPI** (uvicorn) | Backend API the web console talks to. | `http://127.0.0.1:8000` |
| 3 | **Next.js** | Web console (queue, students, reports, settings). | `http://127.0.0.1:3000` |
| 4 | **Pipeline daemon** | Polls Classroom every 60s — answer-key generation, reply parsing, grading workflow. *(Optional during heavy dev — the web console can drive everything by hand.)* | `tools/run_pipeline.py` |

All four are independent. You can start/stop any subset without touching the others.

---

## Start

```bash
# 1. Postgres (one-time per Docker Desktop session; persists across restarts)
docker compose up -d

# 2. Backend (foreground — see logs live). Production mode, no auto-reload.
scripts/start-api.sh

# 3. Frontend (in a separate terminal)
cd web/app && npm run dev

# 4. Pipeline daemon (only if you want auto-AK-generation + auto-grading)
python3 tools/run_pipeline.py
```

Open `http://localhost:3000` — login, queue should load.

**Tip:** to start everything in the background and tail logs separately:

```bash
docker compose up -d
nohup scripts/start-api.sh > .tmp/web-logs/api.log 2>&1 &
(cd web/app && nohup npm run dev > ../../.tmp/web-logs/web.log 2>&1 &)
# Pipeline daemon is loud — keep it foreground or redirect similarly.
```

Logs live under `.tmp/web-logs/`. Tail with `tail -f .tmp/web-logs/api.log`.

### Two API server modes — which to use when

| Script | When to use | Trade-off |
|---|---|---|
| `scripts/start-api.sh` | **Default for normal operation.** Running evaluations, generating reports, day-to-day grading. | No auto-reload — code edits require manual restart. |
| `scripts/dev-api.sh` | **Only** when you're actively editing `web/api/**` or `tools/**` AND no evaluations are queued. | Auto-reloads on save → SIGTERMs the worker process → **kills any in-flight Anthropic call mid-stream** and surfaces as an empty-response failure (the Advaith Govind bug). |

Pick `start-api.sh` unless you have a good reason. The dev script prints a loud
warning banner so you don't accidentally leave it running.

---

## Stop

```bash
# Frontend
# (Ctrl+C in the terminal running `npm run dev`, or kill the bg process)
pkill -f "next dev"

# Backend
pkill -f "uvicorn web.api.main:app"

# Pipeline daemon
pkill -f "python3 tools/run_pipeline.py"

# Postgres — leave running unless you need the laptop's RAM back.
docker compose stop          # graceful — data preserved in the volume
# docker compose down        # also removes the container (volume still preserved)
# docker compose down -v     # ⚠ also wipes the volume — you'll lose all DB rows
```

Reading order matters only one way: **don't `docker compose down -v` casually**. The volume (`evalassign-pgdata`) is where every score / student / AK lives. The `-v` flag is the only destructive one.

---

## Wake from sleep

After a MacBook sleep / lid-close cycle, the usual symptom is the web console getting `500` errors or hanging requests. The fix is short:

```bash
# 1. Is Docker awake?
docker compose ps
# If the row says "Exited" or there's no row, restart:
docker compose up -d

# 2. Is uvicorn alive AND responsive?
# A TCP listener can survive sleep but the process can be deadlocked —
# the thread pool gets exhausted by background jobs that stalled.
curl -s -o /dev/null -w "api: %{http_code} in %{time_total}s\n" \
  --max-time 5 http://127.0.0.1:8000/api/queue
# If you see "000" or it hangs ≥5s, restart it:
pkill -f "uvicorn web.api.main:app"
sleep 2
nohup scripts/start-api.sh > .tmp/web-logs/api.log 2>&1 &

# 3. Frontend usually survives sleep — it's just a long-lived Node process.
# If pages render but every API call 500s, it's #2 above, not Next.js.
```

### Why uvicorn hangs after sleep

`--reload` (used by `scripts/dev-api.sh`) watches files via WatchFiles, which sometimes wedges itself after the kernel pauses fsevents during sleep. The TCP port stays bound but no new requests get serviced. Symptom: `lsof -i :8000` shows it listening, but `curl` times out. Always-safe fix: kill + restart with `scripts/start-api.sh` (data lives in Postgres now, not in memory, so nothing's lost). The default production startup avoids `--reload` entirely, which sidesteps this class of failure.

### Why Postgres usually survives sleep

The container hibernates with the host. On wake, Docker Desktop reanimates it within a few seconds. The volume mount is preserved across host sleeps, restarts, and Docker upgrades. If `docker compose ps` shows it as `Up`, you're fine.

---

## Quick health check (paste-and-run)

```bash
echo "── Postgres ──"
docker compose ps db | tail -1
echo "── Tables + row counts ──"
docker exec evalassign-db psql -U evalassign -d evalassign -c \
  "SELECT 'students' tbl, count(*) FROM students
   UNION ALL SELECT 'scores',           count(*) FROM scores
   UNION ALL SELECT 'answer_key_state', count(*) FROM answer_key_state;"
echo "── API ──"
curl -s -o /dev/null -w "api: %{http_code} in %{time_total}s\n" \
  --max-time 5 http://127.0.0.1:8000/api/queue
echo "── Web ──"
curl -s -o /dev/null -w "web: %{http_code} in %{time_total}s\n" \
  --max-time 5 http://127.0.0.1:3000/
```

Healthy output:

```
── Postgres ──
evalassign-db   Up X minutes (healthy)   ...
── Tables + row counts ──
       tbl        | count
------------------+-------
 students         |    17
 scores           |    15
 answer_key_state |     3
── API ──
api: 200 in 0.04s
── Web ──
web: 200 in 0.20s
```

If any row says `Exited` / `000` / `5xx`, follow the matching restart step above.

---

## Connect to Postgres directly

```bash
# psql via docker exec (no host install needed)
docker exec -it evalassign-db psql -U evalassign -d evalassign

# Or from any GUI client (DBeaver, TablePlus, Postico):
#   host:     127.0.0.1
#   port:     5433        ← NOT the default 5432
#   user:     evalassign
#   password: evalassign
#   database: evalassign
```

The host port is `5433` because port `5432` is already taken by another Docker container (`ck_postgres`). Inside the container it's still `5432`; only the host mapping changes.

---

## Re-migrating from Drive CSV

If `docker compose down -v` ever wipes the volume, or you spin up a fresh dev environment:

```bash
docker compose up -d                # starts the container (schema.sql auto-applies on a fresh volume)
python3 tools/db_migrate.py         # pulls scores.csv + students.csv + answer_key_state.json off Drive into Postgres
```

The migration is idempotent — re-running on a populated DB upserts rather than duplicates.

---

## Credential health & recovery

The system tracks the health of external credentials (Google OAuth, Anthropic API)
in a Postgres table and surfaces failures via the header pill and ops email.

### One-time setup (must be done before the first Reconnect)

1. **Add the OAuth callback URL to Google Cloud Console:**
   - Open https://console.cloud.google.com/ -> APIs & Services -> Credentials
   - Click the OAuth 2.0 Client used by `credentials.json`
   - Under "Authorized redirect URIs", add:
     `http://localhost:8000/api/credentials/google_oauth/oauth-callback`
   - Save.

2. **Publish the OAuth consent screen** (root-cause fix for 7-day refresh-token expiry):
   - OAuth consent screen -> Publishing status
   - If "Testing", click "PUBLISH APP"
   - Scopes (Classroom + Drive + Gmail) are sensitive, but for personal use under
     100 users, Google does not require formal verification.
   - After publishing, refresh tokens no longer auto-expire after 7 days.

3. **Set `OPS_ALERT_EMAIL` in `.env`:**
   ```
   OPS_ALERT_EMAIL=mohitsardana@gmail.com
   ```

4. **Apply the migration once:**
   ```bash
   docker exec -i evalassign-db psql -U evalassign -d evalassign \
     < db/migrations/001_credentials_health.sql
   ```

### Manual smoke test (run once per release)

1. Revoke the token at https://myaccount.google.com/permissions
2. Click "Test now" on the Google card at /settings/credentials (or wait 15 min)
3. Header pill should turn red within 30s.
4. Within 30s, an ops email titled "[evalassign] google_oauth REVOKED" arrives.
5. Click "Reconnect Google" -> complete consent in the new tab.
6. Pill flips green within 30s; a second ops email "[evalassign] google_oauth RECOVERED" arrives.
