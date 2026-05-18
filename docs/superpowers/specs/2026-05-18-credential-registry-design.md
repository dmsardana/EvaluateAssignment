# Credential Registry — Design Spec

**Status:** Approved 2026-05-18 (brainstorm session). Ready for implementation planning.
**Author:** Mohit Sardana (with Claude)
**Scope:** All external auth (Google OAuth + Anthropic API + future credentials)

## 1. Problem

The pipeline depends on two external credentials: a Google OAuth token (`token.json`, used for Drive + Classroom + Gmail) and an Anthropic API key (`ANTHROPIC_API_KEY` in `.env`). Today both can fail silently:

- **Three tools each load Google creds independently** (`tools/run_pipeline.py:35`, `tools/watch_classroom.py:52`, `tools/email_helper.py:20`) with duplicated 5-line blocks. None catch `RefreshError`. A revoked refresh token surfaces as an unhandled exception that crashes whichever tool hit Google first.
- **The token has been refreshed manually twice in seven days** (`token.json.bak.1778486063`, `token.json.bak.1779108766`). The OAuth client is in Google's "Testing" publishing state, so refresh tokens auto-expire after 7 days. This is the actual root cause; the Registry handles the residual failures after that's fixed.
- **No system surface tells the operator a credential is broken** — the user notices when a student report fails to generate, often hours after the failure.
- **The Anthropic key is read directly from `os.environ`** with no validation or visibility. A wrong key fails per-API-call with no system-level signal.

## 2. Goals

1. One uniform abstraction for every external credential — adding a third credential means one file + one `register()` call.
2. Detect breakage proactively (every 15 min) AND reactively (on real failure), so the gap between "token dies" and "operator knows" is bounded.
3. Surface the failure on the existing UI (header pill turns red) AND via email to the operator. Both use existing infrastructure.
4. Provide a one-click "Reconnect Google" / "Update Anthropic key" recovery flow inside the web console. No terminal required for the recovery path.
5. Pipeline tools degrade gracefully when a credential is broken: skip the tick, log loudly, do not crash the daemon.
6. Document and address the root cause (Google OAuth app publication status) so the *frequency* of breakage drops, not just the visibility.

## 3. Non-goals (explicit YAGNI)

| Excluded | Why |
|---|---|
| Slack/Discord/PagerDuty alerts | Single operator. Email is enough. Notifier interface allows future subscribers. |
| Audit log / event-history table | Application logs cover it. Add only when a per-credential timeline view is needed. |
| Multi-user RBAC on `/settings/credentials` | Single operator. Auth.js session gating is sufficient. |
| Auto-rotation of refresh tokens | `google-auth` already handles access-token rotation. Refresh-token rotation matters only in high-security multi-tenant apps. |
| Encryption-at-rest of `token.json` | Single-user laptop, chmod 600, FileVault. App-level encryption would force key management with no threat-model benefit. |
| Generic secrets vault (HashiCorp Vault, AWS Secrets Manager) | Two secrets. Out of scale. |
| Recovery for `credentials.json` itself | If deleted, operator must re-download from Google Cloud Console. We surface as `MISSING` and link the GCP console. |
| Per-scope health checks | All-or-nothing per credential. A missing scope still trips the first API call inside `check_health()`. |

## 4. Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                       Credential Registry                       │
│        (web/api/services/credentials/ — package singleton)     │
│   register("google_oauth", GoogleCredentialHandle())            │
│   register("anthropic_api", AnthropicCredentialHandle())        │
└────────────────────────────────────────────────────────────────┘
        │                  │                       │
        │ check_health()   │ recover()             │ get_client()
        ▼                  ▼                       ▼
 ┌─────────────┐   ┌───────────────────┐   ┌─────────────────────┐
 │ APScheduler │   │ FastAPI endpoints │   │ Pipeline tools      │
 │ every 15 min│   │ /api/credentials  │   │ run_pipeline.py     │
 │             │   │  /reauth, /update │   │ watch_classroom.py  │
 │             │   │                   │   │ email_helper.py     │
 └─────────────┘   └───────────────────┘   └─────────────────────┘
        │                  │                       │
        ▼                  ▼                       ▼
   ┌──────────────────────────────────────────────────────────┐
   │  Postgres: credentials_health table (shared state)       │
   │  + ops-email fan-out on status transitions               │
   └──────────────────────────────────────────────────────────┘
        │
        ▼
   ┌──────────────────────────────────────────────────────────┐
   │  Frontend: header pill + /settings/credentials page      │
   │  polls /api/credentials/status every 30s                 │
   └──────────────────────────────────────────────────────────┘
```

**Three trust zones:**
1. **Read-many** (tools, UI): ask Registry, never touch `token.json` or `.env` directly.
2. **Write-one** (Registry): the only writer of `token.json` and `credentials_health` rows.
3. **Side-effects** (Notifier): subscribes to status transitions, emails on edges only.

## 5. Data model

One new Postgres table. Migration via the existing `tools/db_migrate.py` pattern; DDL added to `db/schema.sql`.

```sql
CREATE TABLE credentials_health (
    name                  TEXT PRIMARY KEY,
    status                TEXT NOT NULL,    -- OK | EXPIRED | REVOKED | MISSING | UNKNOWN
    last_checked_at       TIMESTAMPTZ NOT NULL,
    last_ok_at            TIMESTAMPTZ,
    last_error            TEXT,             -- truncated to 200 chars, token material stripped
    recovery_started_at   TIMESTAMPTZ,      -- non-null while an OAuth flow is in-flight
    notified_at           TIMESTAMPTZ,      -- last ops-email send timestamp (dedupe)
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**State machine:**

```
   UNKNOWN ──check_health() ok──► OK
       │                          │
       │                          │ check_health() fails
       ▼                          ▼
   MISSING ◄───────────── REVOKED | EXPIRED
                                  │
                                  │ user clicks Reconnect
                                  │ recovery_started_at = now()
                                  │ OAuth callback writes token
                                  ▼
                                  OK
```

**Notifier dedupe rule:** email only on `OK → not-OK` and `not-OK → OK` transitions. Hard cap of 1 email per credential per 4 hours regardless of transitions, to handle flapping.

**No history table.** Application logs cover the timeline need.

## 6. Backend components

Five new files, two collapsed.

### 6.1 `web/api/services/credentials/__init__.py` — Registry

```python
class Status(str, Enum):
    OK = "OK"; EXPIRED = "EXPIRED"; REVOKED = "REVOKED"
    MISSING = "MISSING"; UNKNOWN = "UNKNOWN"

class CredentialHandle(Protocol):
    name: str
    def check_health(self) -> tuple[Status, str | None]: ...
    def get_recovery(self) -> RecoveryAction: ...

class Registry:
    def register(self, handle: CredentialHandle) -> None: ...
    def all(self) -> list[CredentialHandle]: ...
    def get(self, name: str) -> CredentialHandle: ...
    def report_status(self, name: str, status: Status, err: str | None) -> None: ...

REGISTRY = Registry()  # module-level singleton, populated by register_defaults()
```

The singleton is populated by `register_defaults()` which runs on import. No FastAPI dependency — CLI tools can import the module standalone.

### 6.2 `web/api/services/credentials/google.py` — `GoogleCredentialHandle`

- Owns `token.json`. Single source of truth for Google creds.
- `check_health()`:
  - If `token.json` missing → `(MISSING, "token.json not found")`.
  - Load creds, call `creds.refresh(Request())` if expired.
  - Map `RefreshError("invalid_grant", ...)` → `REVOKED`. Other `RefreshError` → `EXPIRED`. Unexpected → `UNKNOWN`.
  - On success, atomically persist the refreshed token back to disk.
- `get_recovery()`: returns `RecoveryAction(kind="oauth", start_url="/api/credentials/google_oauth/reauth")`.
- `get_drive()`, `get_classroom()`, `get_gmail()`: thin builders returning `googleapiclient` services. Replace the duplicated auth blocks in three tools.
- Raises `CredentialBroken(name, reason)` from `get_*()` when status is not OK.

### 6.3 `web/api/services/credentials/anthropic.py` — `AnthropicCredentialHandle`

- Reads `ANTHROPIC_API_KEY` from `os.environ` (with `python-dotenv` loaded at module init).
- `check_health()`: if missing → `MISSING`. Otherwise issue a `models.list()` call (cheap, no token spend). 401 → `REVOKED`, 429 → `OK` (rate-limit is not a credential problem), other 4xx/5xx → `UNKNOWN`. Cache results for 5 min.
- `get_recovery()`: returns `RecoveryAction(kind="text_field", field="ANTHROPIC_API_KEY", validate_url="/api/credentials/anthropic_api/update")`.
- `get_client()`: returns the configured `anthropic.Anthropic()` instance; raises `CredentialBroken` when status is not OK.

### 6.4 `web/api/services/credentials/notifier.py` — ops-email fan-out

- Subscribes to `Registry.report_status()`. On transition (`OK ↔ not-OK`), sends a plain-text email via the existing Gmail-send code in `tools/email_helper.py` to `OPS_ALERT_EMAIL` from `.env`.
- Updates `notified_at` so subsequent ticks in the same broken state stay silent.
- Hard cap: max 1 email per credential per 4 hours regardless of transitions.
- If Gmail send itself fails (because `google_oauth` is the broken credential), the notifier logs to stderr and queues a retry; it does NOT call `report_status` recursively (would infinite-loop).

### 6.5 `web/api/routers/credentials.py` — HTTP surface

```
GET  /api/credentials/status
POST /api/credentials/google_oauth/reauth
GET  /api/credentials/google_oauth/oauth-callback
POST /api/credentials/anthropic_api/update
POST /api/credentials/{name}/recheck
```

The OAuth flow:
1. `reauth` starts a `google_auth_oauthlib.Flow` with `redirect_uri = http://localhost:8000/api/credentials/google_oauth/oauth-callback`, returns `{consent_url, state}` JSON.
2. Frontend opens `consent_url` in a new tab.
3. Google redirects back to the callback URL with `code` + `state`.
4. Callback validates `state`, exchanges `code` for tokens, **issues a cheap Drive API call to validate**, then writes `token.json` atomically. Reports `OK` to Registry.
5. Callback HTML triggers `window.close()` and writes a `localStorage` flag the parent page polls.

The callback URL must be added to the Google Cloud Console OAuth client (one-time setup, documented in `OPERATIONS.md`).

### 6.6 `web/api/services/credentials/scheduler.py` — APScheduler job

- `BackgroundScheduler` runs `check_health()` on every registered handle every 15 min.
- Started in FastAPI app `lifespan` startup; stopped on shutdown.
- Configuration: `max_instances=1`, `coalesce=True`, 10s hard timeout per `check_health()` call. Stale ticks can't accumulate; hung endpoints can't stall the scheduler thread.
- Pipeline daemon does NOT run its own scheduler — it calls `REGISTRY.get("google_oauth").check_health()` once per tick (existing ~5-min cadence) for reactive freshness.

### 6.7 Pipeline tools refactor

| File | Before | After |
|---|---|---|
| `tools/run_pipeline.py:35-39` | Inline `Credentials.from_authorized_user_file` + `creds.refresh()` | `classroom = REGISTRY.get("google_oauth").get_classroom()` |
| `tools/watch_classroom.py:52-56` | Same inline block | Same Registry call |
| `tools/email_helper.py:20-24` | Same inline block | `gmail = REGISTRY.get("google_oauth").get_gmail()` |
| `tools/setup_drive.py` | Unchanged | Unchanged — one-time bootstrap, does not go through Registry |

Net: ~40 duplicated lines removed.

Each tool wraps its top-level loop body in `try/except CredentialBroken` → log a single-line `CREDENTIAL_BROKEN google_oauth REVOKED — see /settings/credentials` and skip the tick. Daemon stays up.

## 7. Frontend components

### 7.1 Header pill — `web/app/components/pipeline-pill.tsx` (modify existing)

The current static "Pipeline · live" button becomes the alert surface:

```
Healthy:     [● Pipeline · live]            green dot
Degraded:    [⚠ Credentials · 1 issue]      amber, soft pulse
Broken:      [✖ Credentials · 2 issues]     red, hard pulse
```

Click opens a popover (no navigation):

```
┌────────────────────────────────────────────────┐
│  Credentials                                   │
│  ────────────────────────────────────────────  │
│  ✖ Google (OAuth)    REVOKED    2m ago         │
│      Token has been expired or revoked.        │
│      [ Reconnect Google → ]                    │
│                                                │
│  ● Anthropic API     OK         14m ago        │
│                                                │
│  Manage all → /settings/credentials            │
└────────────────────────────────────────────────┘
```

Data via SWR polling `GET /api/credentials/status` every 30s.

### 7.2 Settings page — `web/app/app/settings/credentials/page.tsx` (new)

Deep-dive view. Absorbs the existing `/settings/anthropic` sidebar link.

Per-credential card with: status, last-check, last-OK, redacted identifier (last 4 of API key, scope count for OAuth), `[Test now]` button (triggers `POST /api/credentials/{name}/recheck`), `[Reconnect →]` or `[Update key ▾]` recovery action.

"Update key" expands inline to `<input>` + `[Validate & save]`. The save button calls `POST /api/credentials/anthropic_api/update` which validates the key (`models.list()` probe) before persisting to `.env`. Invalid keys never touch `.env`.

### 7.3 Reconnect Google flow — client behaviour

1. User clicks "Reconnect Google".
2. Frontend `POST /api/credentials/google_oauth/reauth` → `{consent_url, state}`.
3. Frontend `window.open(consent_url, "_blank")` and shows a non-modal toast.
4. Callback closes the popup via `window.close()` and writes a `localStorage` flag.
5. SWR re-validates within 30s → pill flips green → toast confirms success.

**Failure modes:**

| Case | UI response |
|---|---|
| Consent tab closed without completing | Toast times out at 5 min: "Reconnect cancelled." |
| Google returns `access_denied` | Toast: "Google denied consent." State stays `REVOKED`. |
| New token missing a required scope | Server 400; toast lists missing scopes. |
| `/api/credentials/status` returns 503 | Pill shows grey "Credentials · ?" — never green-by-default while unknown. |

No new frontend dependencies — uses existing SWR + shadcn primitives.

## 8. Error handling

### 8.1 Pipeline tools — fail-loud, not fail-silent

`REGISTRY.get(...).get_classroom()` raises `CredentialBroken` when status is not OK. The tool's top-level handler catches it, logs `CREDENTIAL_BROKEN google_oauth REVOKED — see /settings/credentials`, **skips the tick without crashing the daemon**. Next tick re-checks; if still broken, notifier-dedupe keeps email silent.

### 8.2 Registry — never writes a corrupt token

- `token.json` writes happen via temp-file + `os.replace` (atomic).
- OAuth callback validates the new token with a Drive API call *before* writing. Failure leaves the old `token.json` intact and status stays `REVOKED`.
- Concurrent Reconnect clicks within 5 min of `recovery_started_at` return the existing consent URL instead of starting a new flow.

### 8.3 APScheduler — bounded

- `max_instances=1`, `coalesce=True`. Overrunning ticks are dropped, not queued.
- 10s hard timeout per `check_health()`.
- If the scheduler thread dies, lifespan logs it; pill shows `UNKNOWN` (grey) after 30 min of stale `last_checked_at`. We never fabricate "OK" from staleness.

### 8.4 Notifier — bounded email rate

- Edges only. Hard cap 1 email per credential per 4 hours.
- Recursive Gmail failure logs to stderr, queues retry, does not call `report_status` again.

### 8.5 Frontend — degrades to neutral, not to green

- Loading: grey pill, `"Credentials · …"`.
- 5xx on status endpoint: red `"Credentials · API down"` (distinguishes "creds broken" from "service broken").
- Invalid Anthropic key submission: 400, inline form error, `.env` untouched.

### 8.6 Postgres outage — degraded mode

- Registry falls back to in-memory status (`UNKNOWN` on startup).
- `check_health()` still raises `CredentialBroken` correctly — tools still degrade as designed.
- UI shows `UNKNOWN` for all, with banner: "Credential status unavailable (DB down)."
- Notifier suppresses emails while DB is down (can't compute transitions without history).
- Next scheduler tick after recovery repopulates the table within 15 min.

### 8.7 Security surface

- OAuth callback URL is `localhost:8000`, reachable only from operator's machine.
- `/api/credentials/anthropic_api/update` gated by existing Auth.js middleware.
- `last_error` is truncated to 200 chars and scrubbed of `refresh_token` / `access_token` substrings before persisting.
- `.env` writes use `python-dotenv.set_key` (atomic, preserves comments/quoting).

## 9. Testing strategy

### 9.1 Unit — `web/api/tests/services/test_credentials.py`

| Test | Locks in |
|---|---|
| `test_google_handle_returns_revoked_on_invalid_grant` | `RefreshError("invalid_grant")` → `REVOKED`, `token.json` untouched. |
| `test_google_handle_returns_expired_on_generic_refresh_error` | Generic `RefreshError` → `EXPIRED`. |
| `test_google_handle_missing_token_file` | No `token.json` → `MISSING`, no exception. |
| `test_anthropic_handle_401_is_revoked` | 401 from `models.list()` → `REVOKED`. |
| `test_anthropic_handle_429_is_ok` | Rate-limit → `OK`. |
| `test_anthropic_handle_caches_for_5_min` | Two calls within 5 min → one HTTP call. |
| `test_registry_atomic_token_write` | Killed mid-write → old token still readable. |
| `test_registry_validates_new_token_before_replacing` | New token fails Drive probe → `token.json` keeps old contents, status stays `REVOKED`. |

### 9.2 Notifier — `web/api/tests/services/test_notifier.py`

| Test | Locks in |
|---|---|
| `test_emails_only_on_transition` | 5 consecutive `REVOKED` → 1 email. |
| `test_emails_on_recovery` | `REVOKED → OK` → 2nd email. |
| `test_4h_rate_limit` | 10 flaps in an hour → 1 email. |
| `test_notifier_no_recursion_on_gmail_failure` | Gmail send fails → log, no `report_status` recursion. |

### 9.3 Routers — `web/api/tests/routers/test_credentials.py`

FastAPI TestClient, Registry mocked. Verifies endpoint shapes, OAuth state idempotence (same state token within 5 min), invalid state → 400, invalid Anthropic key → 400 (no `.env` write), Auth.js gating.

### 9.4 Pipeline-tool integration — `tests/test_tools_credential_integration.py`

`tools/watch_classroom.py --once` against a mocked Registry that raises `CredentialBroken`. Asserts: exits 0, stderr contains `CREDENTIAL_BROKEN`, no partial state written.

### 9.5 E2E — `web/e2e/credentials.spec.ts`

1. Seed `credentials_health` with `google_oauth=REVOKED`.
2. Load `/` → pill shows red "Credentials · 1 issue".
3. Click pill → popover lists Google with Reconnect button.
4. Click Reconnect → `window.open` called with URL matching `^https://accounts\.google\.com/`.
5. Simulate callback success → SWR re-validates → pill flips green.

OAuth call to Google is stubbed at the `Flow.fetch_token` boundary. CI never hits live Google.

### 9.6 Manual smoke (added to `OPERATIONS.md`)

5-step checklist exercising real OAuth: revoke at `myaccount.google.com`, wait one tick or click Test Now, verify pill red within 30s, verify ops email received, click Reconnect and complete consent, verify pill green within 30s. Run once per release.

### 9.7 Explicitly not tested

`google_auth_oauthlib`, APScheduler internals, `python-dotenv` parsing, Postgres reliability — all trusted dependencies.

## 10. Rollout

Five waves on a single PR branch. Reviewer-friendly chunks, not deploy chunks (we merge once at the end).

| Wave | Scope | Stand-alone value |
|---|---|---|
| 1 | Registry + Google handle. Refactor 3 pipeline tools. No DB yet — in-memory status. | Kills duplicated auth code; tools stop crashing on `RefreshError`. |
| 2 | `credentials_health` table + Notifier + `OPS_ALERT_EMAIL` env var. | Operator gets ops email even before UI exists. |
| 3 | FastAPI router + APScheduler. Add callback URL to Google Cloud Console. | `curl /api/credentials/status` works; CLI reauth via consent URL. |
| 4 | `AnthropicCredentialHandle` + update endpoint. | Second credential proves the abstraction. |
| 5 | Frontend pill + settings page. | One-click reconnect loop closed. |

## 11. Root-cause fix (operator action, outside the code change)

The most important item in this spec. Without it, the Registry keeps you alive but the underlying refresh-token problem keeps recurring.

**Steps** (also added to `OPERATIONS.md`):

1. Open Google Cloud Console → APIs & Services → OAuth consent screen for the project owning `credentials.json`.
2. Check **Publishing status**. If "Testing", click **Publish app**.
3. Confirm scopes (Classroom + Drive + Gmail are sensitive but **for personal use under 100 users, Google does not enforce formal verification** — consent screen shows an "unverified" warning, which is acceptable for a single-operator tool).
4. After publishing, refresh tokens no longer auto-expire after 7 days. They die only on explicit user revoke or 6-month inactivity.

After this is done, expected `REVOKED` frequency drops from "once a week" to "essentially never."

**Additional one-time setup:** add `http://localhost:8000/api/credentials/google_oauth/oauth-callback` to the OAuth client's authorized redirect URIs in Google Cloud Console.

## 12. Documentation deliverables

- `OPERATIONS.md`: new top-level section **"Credential health & recovery"** — operator-facing view, includes the OAuth-publication root-cause steps and the manual smoke checklist.
- `CLAUDE.md`: one sentence under the existing "Credentials" section: *"All API credential access goes through `web.api.services.credentials.REGISTRY`. Do not load `token.json` or read `ANTHROPIC_API_KEY` from `os.environ` directly in new code."*
- The one-shot `/tmp/reauth_google.py` script from the 2026-05-18 session is deleted — superseded by the UI flow.

## 13. Acceptance criteria

The design is delivered when, in a fresh environment:

1. Revoking the token at `myaccount.google.com` causes the header pill to turn red within 15 min (or 30s with "Test now").
2. Exactly one ops email arrives within 30s of the transition.
3. Clicking "Reconnect Google" in the header popover opens a Google consent tab.
4. Completing the consent flow flips the pill back to green within 30s; second ops email arrives.
5. Killing the FastAPI process mid-token-write leaves a valid `token.json` (the previous one) — never a half-written file.
6. Pipeline daemon, run against a revoked token, logs `CREDENTIAL_BROKEN` and continues looping without exiting.
7. The Google OAuth app is in **Published** state in Google Cloud Console.
