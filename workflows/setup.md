# Workflow: Initial Setup

**Run once** before using the evaluation pipeline.

## Prerequisites

1. **Google Cloud Project** with these APIs enabled:
   - Google Drive API
   - Google Classroom API
   - Gmail API
2. **OAuth 2.0 Desktop credentials** downloaded as `credentials.json` in the project root.
3. **Python 3.10+** installed.
4. **Tectonic** (LaTeX engine) — installed at project root as `./tectonic`.
   Direct install: `curl --proto '=https' --tlsv1.2 -fsSL https://drop-sh.fullyjustified.net | sh`

## Steps

### 1. Install Python dependencies
```bash
pip3 install -r requirements.txt
```

### 2. Configure .env
Copy `.env.example` to `.env` and fill in:
```
ANTHROPIC_API_KEY=sk-ant-...
DRIVE_ROOT_ID=<root folder ID from your Drive URL>
TEACHER_EMAIL=you@example.com
PDFLATEX_PATH=/absolute/path/to/tectonic
CUTOFF_DATE=YYYY-MM-DD     # only process submissions on/after this date
EVALUATOR_MODEL_WA=claude-sonnet-4-6
EVALUATOR_MODEL_QA=claude-opus-4-7
EVALUATOR_MODEL_AA=claude-opus-4-7
```

### 3. Run setup
```bash
python3 tools/setup_drive.py
```

This will:
- Open a browser for Google OAuth consent (first run only)
- **Tick every checkbox** when granting permissions — Drive, Classroom (4 scopes), Gmail send + read
- Create `answer_keys/` and `reports/` subfolders under `DRIVE_ROOT_ID`
- List all your active Google Classroom courses and write their IDs to `.env`

If you have multiple courses, edit `CLASSROOM_COURSE_IDS` in `.env` to keep only relevant ones.

### 4. Tell students how to label assignments in Google Classroom
The system auto-detects the assignment **type** and **code** from the assignment title. Use one of these formats:

| Format | Example title | Detected |
|---|---|---|
| Parenthetical | `02b A01 Continuity (Code: QA DA-MT-2025 CG-LCD-01)` | type=QA, code=DA-MT-2025_CG-LCD-01 |
| Pipe-delimited | `07 Domain \| Code: DOM3 \| Type: QA` | type=QA, code=DOM3 |
| Bracketed | `04 Logarithms [QA]` | type=QA, code=04 (number fallback) |

Students attach their handwritten PDF as the submission attachment in Google Classroom.

### 5. Verify
```bash
python3 tools/watch_classroom.py
```
Should print the JSON list of pending submissions and confirm setup works end-to-end.

## Notes
- `token.json` is created automatically after first OAuth and is gitignored.
- ZA (Quiz Assignments) use Google Forms and are excluded from this pipeline.
- Progression thresholds: WA ≥ 60% → qualifies for QA; QA ≥ 75% → qualifies for AA.
