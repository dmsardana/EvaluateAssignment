# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A pipeline that auto-grades handwritten student PDFs from Google Classroom against an AI-generated, teacher-approved answer key. Built on the **WAT framework** (Workflows, Agents, Tools) — probabilistic reasoning (Claude vision) for grading + deterministic Python for orchestration. Final outputs are PDF reports + a `scores.csv` log uploaded to Google Drive.

For day-to-day operation see [RUNBOOK.md](RUNBOOK.md).

## Architecture

Three layers, strictly separated:

- **`workflows/`** — Markdown SOPs: setup, evaluate_assignment, generate_answer_key. Source of truth for what to do and how.
- **`tools/`** — Python scripts. Each is single-purpose and independently runnable. Load credentials from `.env`.
- **`.tmp/`** — Disposable scratch. Regenerable.

Final outputs (report PDFs, scores.csv, answer keys, state JSON) live in Drive — not locally.

## Pipeline Flow (Cliff-Notes)

1. **`run_pipeline.py`** orchestrates everything. Each tick:
2. **`generate_answer_key.py`** — for any new coursework without an APPROVED state, pulls the question paper from Classroom, calls Claude (Opus 4.7 for QA/AA, Sonnet 4.6 for WA), renders LaTeX → PDF, uploads to Drive `answer_keys/`, emails teacher with OTP.
3. **`check_review_replies.py`** — polls Gmail for replies. Approves keys (`OK <OTP>`) or auto-regenerates flagged questions (`Q3 reprocess <OTP>` or `Wrong, redo all <OTP>`). Strips quoted email content; auths via Gmail-verified From address.
4. **`watch_classroom.py`** — lists pending TURNED_IN submissions (filtered by `CUTOFF_DATE`).
5. For submissions whose answer key is APPROVED:
   - **`download_pdf.py`** fetches student PDF + matching key
   - **`evaluate_pdf.py`** sends both to Claude vision; outputs rich JSON (5-dim rubric × N questions, concept map, SWOT, misconceptions, 3 improvement priorities, closing note, scan quality)
   - **`generate_report.py`** renders LaTeX (using `tools/templates/ts_evalreport.sty`) and compiles via tectonic
   - **`upload_report.py`** uploads to Drive `reports/`
   - **`track_scores.py`** appends to `scores.csv` on Drive

## Key Conventions

- **Assignment titles** are parsed for type (WA/QA/AA) and code. Three accepted formats: `(Code: TYPE IDENTIFIER)`, `Type: XX | Code: YYY`, or `[XX]` with leading number. See `tools/watch_classroom.py:parse_assignment_meta`.
- **Per-question rubric**: continuous 0..1 per dimension (rounded to 2 decimals — full range, not 0/0.5/1 buckets); weights 0.40/0.20/0.20/0.10/0.10. Per-question score capped at 1.00. Weights are locked; the dimension scale itself is intentionally continuous so aggregates land at fractional percentages like 33.3%, 67.4%, etc.
- **Performance bands**: Trailblazer ≥75%, Qualifier 60–74%, Developing 45–59%, Foundational Gaps <45%.
- **Report style** is defined in `tools/templates/ts_evalreport.sty` (copied from `references/templates/`). Compilation requires `xelatex` features — tectonic handles this. Fonts (TeX Gyre Heros + Latin Modern Math) are bundled in `tools/templates/*.otf`.
- **Filename pattern** for reports: `{StudentName}_{CODE}_{YYYY-MM-DD}_Report.pdf`. StudentName is CamelCase, no spaces, diacritics stripped.
- **State for AK approval** lives at `answer_keys/answer_key_state.json` on Drive. Status values: GENERATING, PENDING_REVIEW, NEEDS_REGEN, APPROVED. Grading is gated on `APPROVED`.

## Running Tools

```bash
python3 tools/run_pipeline.py            # continuous polling
python3 tools/run_pipeline.py --once     # one-shot, then exit
python3 tools/<other_script>.py          # individual tools (see RUNBOOK)
```

No build system. Tools are standalone Python scripts with credentials from `.env` (via `python-dotenv`).

The **web console + FastAPI** layer is a separate process. Start it via `scripts/start-api.sh` (production, no auto-reload — safe to run during evaluations). Use `scripts/dev-api.sh` only when actively editing API code; its `--reload` SIGTERMs in-flight workers and corrupts long Anthropic calls (this caused the Advaith Govind empty-response bug). See [OPERATIONS.md](OPERATIONS.md#two-api-server-modes--which-to-use-when) for the full distinction.

## Working in This Repo

**Before writing new code:** Check `tools/` for an existing script. Only create new tools when nothing fits.

**When adding a tool:** Single-purpose Python script in `tools/`. Load secrets from `.env` only — never hardcode credentials.

**When a tool fails:** Read the full error, fix the script, retest. If the fix involves paid API calls, confirm with the user first. Then update the workflow file with what you learned (rate limits, batch endpoints, timing quirks) so the failure doesn't recur.

**Updating workflows:** Edit `workflows/*.md` when you find better approaches or encounter recurring issues. Do not create or overwrite workflow files without explicit user instruction — these are living operational docs, not disposable scratch.

## Credentials

`.env` is the only place for API keys and secrets (gitignored). Google OAuth uses `credentials.json` + `token.json` (both gitignored).

All API credential access goes through `web.api.services.credentials.REGISTRY`. Do not load `token.json` or read `ANTHROPIC_API_KEY` from `os.environ` directly in new code. To use Google APIs:

```python
from web.api.services.credentials import REGISTRY
classroom = REGISTRY.get("google_oauth").get_classroom()
```

If the credential is broken, `get_*()` raises `CredentialBroken`; pipeline tools catch this in their `tick()` handler and skip the tick without crashing. See [OPERATIONS.md](OPERATIONS.md) → "Credential health & recovery" for operator setup and the smoke test.
