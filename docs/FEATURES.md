# EvaluateAssignment — Exhaustive Feature List

An end-to-end auto-grading pipeline for handwritten student PDFs from Google Classroom, paired with a web console for operators. Built on the **WAT framework** (Workflows, Agents, Tools) — Claude vision for probabilistic grading + deterministic Python for orchestration. Structured state (scores, students, answer-key approval state) lives in **Postgres** per [`db/schema.sql`](../db/schema.sql); generated PDFs (reports, answer keys) live in **Google Drive**. The legacy `scores.csv` / `students.csv` / `answer_key_state.json` files on Drive are now fallback mirrors retained for migration and out-of-band edits.

This document is the canonical feature inventory. For day-to-day operation see [RUNBOOK.md](../RUNBOOK.md); for service lifecycle see [OPERATIONS.md](../OPERATIONS.md).

---

## 1. Grading Pipeline (Python `tools/`)

### 1.1 Orchestration
- **`run_pipeline.py`** — single entry point; continuous polling daemon by default
- `--once` flag for one-shot mode (process everything pending now, then exit)
- Per-tick lifecycle: answer-key generation → review-reply polling → submission watch → per-submission grading
- Catches `CredentialBroken` per tick and skips the tick without crashing the daemon
- Graceful shutdown via SIGINT; logs each stage transition
- Honors `CUTOFF_DATE` to ignore old submissions

### 1.2 Answer Key Generation (`generate_answer_key.py`)
- Pulls question paper PDF from Google Classroom for each new coursework
- Sends PDF to Claude vision; model selected per **tier** (Opus 4.7 for QA/AA, Sonnet 4.6 for WA)
- Renders LaTeX answer key via Jinja2 (`answer_key_template.tex`) with math-safe delimiters
- Compiles to PDF via **tectonic** (no system xelatex required)
- Uploads to Drive `answer_keys/` folder
- Initializes per-coursework state in `answer_key_state.json` with status `GENERATING` → `PENDING_REVIEW`
- Sends teacher review email with a one-time OTP via `email_helper.py`
- Supports targeted regeneration of only questions flagged `needs_rework`

### 1.3 Answer-Key Review Loop (`check_review_replies.py`, `email_helper.py`, `review_state.py`)
- Polls Gmail thread for teacher replies
- Authorizes only replies whose From matches the verified teacher Gmail
- Strips quoted reply content before parsing
- Reply formats recognized:
  - `OK <OTP>` → approve full key (status → `APPROVED`)
  - `Wrong, redo all <OTP>` → mark entire key for regeneration
  - `Qn reprocess <OTP>` (e.g. `Q3 reprocess 482917`) → mark a single question for redo
- Per-question status tracking inside `answer_key_state.json` (`questions_status[]`)
- Tracks `regen_count`, `thread_id`, `approved_at` timestamp
- `is_approved()` gate — grading does not proceed until status is `APPROVED`

### 1.4 Submission Watch (`watch_classroom.py`)
- Lists TURNED_IN submissions across configured Classroom courses
- Filters by `CUTOFF_DATE` so old work isn't reprocessed
- Parses assignment titles in three accepted formats:
  - `(Code: TYPE IDENTIFIER)` e.g. `(Code: QA WORK-12)`
  - `Type: XX | Code: YYY`
  - `[XX]` with leading number
- Case-insensitive matching on `WA`/`QA`/`AA`/`ZA`
- Returns coursework + submission tuples ready for evaluation

### 1.5 Student PDF Download (`download_pdf.py`)
- Streams PDF attachments via `MediaIoBaseDownload` (resumable)
- Case-insensitive filename matching across attachments
- 404 detection on missing/revoked files
- Writes to local scratch (`.tmp/`); never authoritative storage

### 1.6 Vision Grading (`evaluate_pdf.py`)
- Sends student PDF + approved answer key to Claude vision as base64 documents
- Model is overridable per-tier via `EVALUATOR_MODEL_<TYPE>` env vars
- Token cap: 16 000 output tokens per evaluation
- Produces structured JSON: per-question 5-dim rubric, weighted total, concept map, SWOT, misconceptions, 3 improvement priorities, closing note, scan-quality flag
- **Numerical Accuracy is binary** per atomic claim (1 or 0; no partial credit)
- Multi-claim NA scored as `k/n`
- Generates a tracking ID for score correlation
- Cached evaluations stored under `web/api/_eval_cache/`

### 1.7 Report Compilation (`generate_report.py`)
- Renders student PDF report via Jinja2 with conservative LaTeX escaping (preserves math)
- Uses `tools/templates/report_template.tex` + `ts_evalreport.sty`
- Bundled fonts: TeX Gyre Heros (sans), Latin Modern Math
- Filename pattern: `{StudentName}_{CODE}_{YYYY-MM-DD}_Report.pdf` (CamelCase, diacritics stripped)
- Supports re-rendering without re-evaluating (reuses cached evaluation JSON)
- Closing-note constraint: must not reference future-assignment promises
- Anti–"0.05 bucketing" rule for rubric scores (forces full continuous range)

### 1.8 Drive Distribution
- **`upload_report.py`** — `MediaFileUpload` with `resumable=True`; deletes stale older reports before upload
- **`return_to_classroom.py`** — shares report with student via Drive reader permission, sends HTML+plain-text email with view link, dedupes permissions on 409
- **`lockdown_drive_file.py`** — sets `copyRequiresWriterPermission=True`, `viewersCanCopyContent=False`, `writersCanShare=False`
- Helper trio: `apply_view_lockdown()`, `verify_view_lockdown()`, `ensure_view_lockdown()` (idempotent)
- `is_drive_404()` helper for safe permission verification

### 1.9 Score Tracking (`track_scores.py`)
- Persists scores to the Postgres **`scores`** table — primary store (`PRIMARY KEY (assignment_type, assignment_code, student_id)`)
- Continues to mirror to `scores.csv` on Drive as a legacy fallback (the migration path documented in OPERATIONS.md still uses it)
- Extracts percentage from Claude evaluation JSON; populates per-dimension averages (`concept_pct`, `approach_pct`, `steps_pct`, `accuracy_pct`, `clarity_pct`)
- Records `coursework_id`, `eval_started_at`/`eval_completed_at`, `linked_at`/`unlinked_at`, `report_drive_id` — fields the web console's scores matrix and link/unlink flow rely on
- Deduplication is enforced by the primary key (atomic upsert), not by application-side `(type, code, student_id)` filtering

### 1.10 Persistence (`db.py`, `student_profiles.py`)
- Lightweight Postgres wrapper using `psycopg_pool.ConnectionPool` (min 1, max 8, 10 s timeout)
- Helpers: `get_pool()`, `fetch_one()`, `fetch_all()`, `execute()`, `execute_many()`
- Loads `DATABASE_URL` via python-dotenv
- **Three primary tables**, all defined in `db/schema.sql`:
  - `scores` — every graded submission, keyed by `(assignment_type, assignment_code, student_id)`
  - `students` — roster + editable display name / email / mobile; trigger-bumped `updated_at`
  - `answer_key_state` — per-coursework AK approval workflow (`DETECTED | GENERATING | PENDING_REVIEW | NEEDS_REGEN | APPROVED`), questions JSONB, OTP, regen counter
  - `credentials_health` — health snapshots written by the credential scheduler
- Drive CSV / JSON files (`scores.csv`, `students.csv`, `answer_key_state.json`) are the **legacy fallback layer** the Postgres tables replaced — kept for migration and out-of-band edits via `tools/db_migrate.py`
- Thread-safe with `_PROFILE_LOCK`
- `update_profile()` uses `INSERT … ON CONFLICT` upsert

### 1.11 Setup & Config
- **`setup_drive.py`** — one-time `InstalledAppFlow` OAuth, provisions `answer_keys/`, `reports/`, `students/` folders, lists courses for `.env`
- Writes `OAUTHLIB_RELAX_TOKEN_SCOPE=1` workaround for refresh edge cases
- **`tier_config.py`** — central tier ladder (`WA→QA→AA terminal`, `ZA→terminal pass`); pass-percentage defaults (WA 60, QA 75, AA none); env overrides via `TIER_PASS_PCT_<TIER>`

### 1.12 LaTeX Templates (`tools/templates/`)
- `answer_key_template.tex` — Jinja2-driven answer-key layout
- `report_template.tex` — student report layout
- `ts_evalreport.sty` — house typography & rubric tables
- `logo.png` — embedded header logo
- `latinmodern-math.otf`, `texgyreheros-*.otf` — bundled fonts

---

## 2. Web Console (Next.js `web/app/`)

### 2.1 Pages
| Path | Purpose |
| --- | --- |
| `/` | Root landing |
| `/welcome` | First-run onboarding surface |
| `/assignments` | Coursework list with tier, status, submission counts |
| `/students` | Roster + editable profile (display name, email, mobile) |
| `/queue/[coursework_id]` | Per-assignment queue view: answer-key state, submissions, evaluation progress, link-to-Classroom controls |
| `/reports` | Generated report list, Drive view links |
| `/scores` | Cross-assignment score matrix |
| `/rubric` | Live rubric reference (dimensions, weights, bands) |
| `/settings/classroom` | Classroom integration controls |
| `/settings/workspace` | Workspace-level config |
| `/settings/credentials` | Credential health + Anthropic API key update form |
| `/settings/billing` | Billing surface |
| `/account/security` | Account security controls |

### 2.2 Shell / Chrome Components
- `shell.tsx`, `top-bar.tsx`, `side-nav.tsx`, `page-chrome.tsx` — global layout
- `user-menu.tsx` — current-user menu
- `collapsible-section.tsx` — accordion sections
- `math.tsx` — KaTeX math rendering
- `model-picker.tsx` — model selection control

### 2.3 Credentials UX
- `credentials-popover.tsx` — shell-level popover triggered from the pipeline pill
- `pipeline-pill.tsx` — live health pill in the top bar, SWR-driven
- `credentials-cards.tsx` — per-credential cards (Google OAuth, Anthropic)
- `lib/credentials.ts` — `useCredentials()` SWR hook, `startGoogleReauth()`, `updateAnthropicKey()`, `recheckCredential()`, `useWatchReauthCompletion()`
- Reconnect Google flow: opens consent URL, polls completion, auto-refreshes status
- "Test now" button forces an immediate credential recheck

### 2.4 Frontend API Client (`lib/api.ts`)
Strongly typed wrapper around every backend endpoint:
- Queue: `queue()`, `queueItem(id)`, `approve(id)`, `abort(id)`, `generate(id)`, `reprocess(id, body)`, `evaluate(id, body)`, `evaluationsAbort(id)`, `evaluationsProgress(id)`, `bulkProgress(id)`
- Submissions: `shareSubmission`, `unshareSubmission`, `linkSubmission`, `unlinkSubmission`, `linkAll`, `unlinkAll`
- Questions: `setQuestionStatus(id, n, status)`
- Reports / Students / Scores: `reports()`, `students()`, `setStudent()`, `scoresMatrix()`
- Dashboards: `stats()`, `budget()`, `distribution()`
- Settings: `rubric()`, `thresholds()` / `setThresholds()`, `tierCutoffs()` / `setTierCutoffs()`
- Type exports: `AssignmentType`, `QueueStatus`, `Band`, `QuestionStatus`, plus 25+ interfaces

### 2.5 Preferences
- `lib/preferences.ts` — client-side UI preferences (e.g. collapsed sections)

### 2.6 E2E Tests
- `web/app/e2e/credentials.spec.ts` — Playwright coverage of credentials popover, Reconnect Google, Anthropic key update
- `playwright.config.ts` — local Playwright config

---

## 3. FastAPI Backend (`web/api/`)

### 3.1 App-level (`main.py`)
- `GET /api/health` — liveness
- `GET /api/budget` — current Anthropic API budget snapshot
- `GET /api/distribution` — band distribution stats across students
- `GET /api/stats` — global counters (assignments, evaluations, reports)
- CORS middleware for frontend origin

### 3.2 Credentials Router (`routers/credentials.py`)
- `GET /api/credentials/status` — health snapshot for all registered credentials
- `POST /api/credentials/{name}/recheck` — force re-validation of a single credential
- `POST /api/credentials/google_oauth/reauth` — start OAuth consent flow; returns `{consent_url, state}`
- `GET /api/credentials/google_oauth/oauth-callback` — OAuth redirect target (HTML response page)
- `POST /api/credentials/anthropic_api/update` — replace Anthropic key in `.env`

### 3.3 Queue Router (`routers/queue.py`)
- `GET /api/queue` — list all queue items with status pills
- `GET /api/queue/{id}` — detail: coursework metadata, submissions, answer-key state, questions, materials
- `POST /api/queue/{id}/evaluate` — start evaluation batch for an assignment
- `GET /api/queue/{id}/evaluations/progress` — per-submission progress for in-flight evaluations
- `POST /api/queue/{id}/evaluations/abort` — cancel in-flight evaluations
- `POST /api/queue/{id}/approve` — approve answer key (skips email-loop for manual approval)
- `POST /api/queue/{id}/abort` — abort queue item
- `POST /api/queue/{id}/questions/{n}/status` — mark question as `pending`/`approved`/`needs_rework`
- `POST /api/queue/{id}/reprocess` — kick off targeted answer-key regeneration
- `POST /api/queue/{id}/generate` — start initial answer-key generation
- `POST /api/queue/{id}/upload-key` — upload a manually authored answer key
- `POST /api/queue/{id}/submissions/{student_id}/link` — share a graded report back to a student
- `POST /api/queue/{id}/submissions/{student_id}/unlink` — revoke a shared report
- `POST /api/queue/{id}/link-all-graded` — bulk share all graded reports
- `POST /api/queue/{id}/unlink-all-linked` — bulk revoke
- `GET /api/queue/{id}/bulk-progress` — progress for bulk link/unlink

### 3.4 Students Router (`routers/students.py`)
- `GET /api/students` — roster with display name, email, mobile, course enrolments
- `PUT /api/students/{student_id}` — patch profile fields

### 3.5 Reports Router (`routers/reports.py`)
- `GET /api/reports` — report rows with Drive view URLs, share status, scores

### 3.6 Scores Router (`routers/scores.py`)
- `GET /api/scores-matrix` — courses × students × assignments score grid with band classification

### 3.7 Settings Router (`routers/settings.py`)
- `GET /api/settings/rubric` — dimensions, weights, descriptions
- `GET /api/settings/thresholds` / `PUT` — band cutoffs (Trailblazer / Qualifier / Developing / Foundational Gaps)
- `GET /api/settings/tier-cutoffs` / `PUT` — tier pass percentages per WA/QA/AA/ZA

### 3.8 Wire Router (`routers/wire.py`)
- `GET /api/wire` — activity wire / event stream

### 3.9 Models (`models.py`)
30+ Pydantic models including: `Question`, `Material`, `SubmissionAttachment`, `Submission`, `QueueItem`, `QueueDetail`, `GenerationProgress`, `ApproveRequest`, `ReprocessRequest`, `SetQuestionStatusRequest`, `EvaluateRequest`, `EvaluationStartResponse`, `EvalProgressEntry`, `EvalProgressResponse`, `CourseEnrolment`, `StudentProfile`, `StudentProfilePatch`, `ScoreMatrixAssignment`, `ScoreMatrixStudent`, `ScoreCell`, `ScoreMatrixCourse`, `ScoreMatrixResponse`, `ReportRow`, `WireItem`, `DistributionResponse`, `StatsResponse`, `BudgetResponse`, `RubricDimension`, `Thresholds`, `TierCutoffs`, `RubricResponse`

### 3.10 Services
- **`services/credentials/__init__.py`** — `REGISTRY` singleton, `Registry` class, `CredentialHandle` protocol, `CredentialBroken` exception, `Status` enum, `RecoveryAction`, `HealthSnapshot`, subscription hooks for transitions
- **`services/credentials/google.py`** — `GoogleCredentialHandle` (OAuth refresh, Classroom/Drive/Gmail client factories)
- **`services/credentials/anthropic.py`** — `AnthropicCredentialHandle` (`.env`-backed key, ping check)
- **`services/credentials/register_defaults.py`** — boots Google + Anthropic handles, attaches notifier
- **`services/credentials/scheduler.py`** — APScheduler job running `check_health()` across all handles
- **`services/credentials/notifier.py`** — emails operator on credential transitions
- **`services/credentials/store.py`** — persisted health-snapshot storage
- **`services/queue.py`** — queue listing, detail, generation orchestration, link/unlink helpers, eval-cache, in-process generation-progress map, `GenerationCancelled`, share/lockdown integration, `_send_approval_email`

### 3.11 Tests
- `web/api/tests/` — pytest suite for backend routes/services

---

## 4. Rubric, Scoring & Tier Model

- **5 rubric dimensions** with locked weights:
  - Numerical Accuracy — 0.40
  - Methodology — 0.20
  - Presentation — 0.20
  - Reasoning — 0.10
  - Closure — 0.10
- Each dimension continuous **0..1**, rounded to 2 decimals (full range, not 0/0.5/1 buckets)
- Per-question score capped at 1.00
- **Numerical Accuracy is binary** per atomic claim; `k/n` for multi-part
- **Performance bands**: Trailblazer ≥75%, Qualifier 60–74%, Developing 45–59%, Foundational Gaps <45%
- **Tier ladder**: WA (60→QA), QA (75→AA), AA terminal, ZA (75→pass terminal)
- Tier overrides via `TIER_PASS_PCT_<TIER>`
- Operators can adjust band cutoffs and tier cutoffs live via `/api/settings/thresholds` and `/api/settings/tier-cutoffs`

---

## 5. Answer-Key Approval State Machine

- States: `GENERATING` → `PENDING_REVIEW` → `NEEDS_REGEN` → `APPROVED`
- State file: `answer_keys/answer_key_state.json` on Drive (one entry per coursework)
- Per-entry fields: status, OTP, thread_id, regen_count, questions_status[], approved_at, drive_id
- Approval gate: only `APPROVED` keys participate in grading
- Two approval surfaces:
  - **Email OTP** — teacher replies to review email (`check_review_replies.py`)
  - **Web console** — `POST /api/queue/{id}/approve` from `/queue/[coursework_id]`
- Targeted regeneration via question-level `needs_rework` status

---

## 6. Credentials Architecture

- Single source of truth: `web.api.services.credentials.REGISTRY`
- Two registered handles: `google_oauth`, `anthropic_api`
- `get_*()` raises `CredentialBroken` on failure → pipeline skips tick, web returns 503-style status
- Background scheduler (`APScheduler`) periodically calls `check_health()` on each handle
- Notifier emails operator on status transitions (e.g. `OK → BROKEN`)
- Full OAuth re-consent flow exposed via `/api/credentials/google_oauth/reauth`
- Anthropic key rotation via `/api/credentials/anthropic_api/update` (rewrites `.env`)
- All API access goes through the registry — new code must never read `token.json` or `ANTHROPIC_API_KEY` directly

---

## 7. Operations

### 7.1 Four Services
1. **Postgres** — Docker Compose container, port `5433` host → `5432` container
2. **FastAPI backend** — uvicorn on port 8000
3. **Next.js frontend** — `npm run dev` (or production build), port 3000
4. **Pipeline daemon** — `tools/run_pipeline.py` (optional; only for auto-AK + auto-grading)

### 7.2 Two API Server Modes
- **`scripts/start-api.sh`** — production mode, no `--reload`, **safe to run during evaluations**
- **`scripts/dev-api.sh`** — `--reload` enabled; only for active API code editing
- Documented bug: `--reload` SIGTERMs in-flight workers and can corrupt long Anthropic vision calls (the Advaith Govind empty-response bug)

### 7.3 Wake-from-Sleep Protocol
- Check Docker container is awake (`docker ps`)
- Verify uvicorn is alive AND responsive (TCP can survive sleep while thread pool deadlocks)
- Frontend usually survives sleep; if every API call 500s, backend is the culprit
- Documented quick-health-check one-liner in OPERATIONS.md

### 7.4 Database Access
- Direct shell: `docker exec` → `psql`
- GUI clients: host `127.0.0.1`, port `5433`, user/pass/db `evalassign`

### 7.5 Re-migration & Recovery
- "Re-migrating from Drive CSV" recipe documented in OPERATIONS.md
- Manual smoke test for credential health (per release)
- One-time setup notes for first Reconnect

### 7.6 Cost Tracking
- Per-pipeline-run cost expectations in RUNBOOK.md
- Live budget via `GET /api/budget`

---

## 8. Workflows / SOPs (`workflows/`)

- **`setup.md`** — initial install: Python deps, `.env`, `setup_drive.py`, teaching staff how to label assignments
- **`generate_answer_key.md`** — state machine, trigger commands, OTP reply formats, polling, state-file schema, cost notes, prompt tuning guidance
- **`evaluate_assignment.md`** — prerequisites, running the pipeline, rubric reference, bands, report structure, outputs, re-render without re-evaluate, error handling

These are living docs — updates are appended whenever a recurring issue or better approach is discovered.

---

## 9. Repository Conventions

- `.env` is the only place for secrets (gitignored)
- `credentials.json` + `token.json` for Google OAuth (gitignored)
- Authoritative state lives in **Postgres** (`scores`, `students`, `answer_key_state`, `credentials_health`); generated **PDFs** (reports, answer keys) live in **Google Drive**; the legacy `scores.csv` / `students.csv` / `answer_key_state.json` on Drive are kept only as migration fallbacks
- `.tmp/` is disposable scratch
- No build system for tools — each `tools/*.py` is independently runnable
- Web app has its own `package.json` + `requirements.txt` for backend
- Test suite under `tests/` (Python) and `web/app/e2e/` (Playwright)

---

## 10. Cross-Cutting Behaviors

- **Tier-aware model selection** wired end-to-end (CLI tools, FastAPI, web UI badges)
- **Idempotent retries** for Drive ops (lockdown verification, duplicate report deletion, 409 dedupe)
- **Concurrency safety** via thread locks in profile management
- **OTP-based authorization** for teacher email actions
- **Live SWR refresh** on the frontend for credential and queue state
- **CredentialBroken-aware** error model — pipeline degrades gracefully instead of crashing
- **Eval cache** at `web/api/_eval_cache/` enables re-rendering reports without re-spending Claude tokens
