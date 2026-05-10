# Workflow: Evaluate Assignment

**Purpose:** Grade newly submitted student PDFs from Google Classroom against an APPROVED answer key, produce a ThinkingSouls-style LaTeX PDF report (cover, snowflake chart, concept map, misconceptions, SWOT, improvements, per-question cards, closing note), upload to Drive, and track progression eligibility.

## Prerequisites
- `workflows/setup.md` already run (`.env` populated, OAuth token saved, Tectonic installed)
- Answer key for each coursework is **APPROVED** via the email loop (`workflows/generate_answer_key.md`)
- Students have submitted PDFs via Google Classroom

## Running the Pipeline

```bash
# Continuous polling loop (Ctrl+C to stop)
python3 tools/run_pipeline.py

# One-shot: process everything pending now and exit
python3 tools/run_pipeline.py --once
```

Each tick the orchestrator does the following in order:

1. **Auto-generate answer keys** for any coursework without an APPROVED state → emails you for review
2. **Check Gmail** for review replies → marks APPROVED or auto-regenerates flagged questions
3. **List pending submissions** (TURNED_IN, not in `scores.csv`, on/after `CUTOFF_DATE`)
4. **For each submission whose key is APPROVED:**
   - Download student PDF + answer key
   - Evaluate via Claude vision (Opus 4.7 for QA/AA, Sonnet 4.6 for WA)
   - Render LaTeX → compile PDF via tectonic
   - Upload report PDF to Drive `reports/`
   - Append row to `scores.csv`

Submissions whose keys aren't yet approved are **skipped** with a `⏸ SKIP (key not approved)` log line.

## Rubric (Standard Subjective)

| Dimension                | Weight | Code | Score scale |
|--------------------------|--------|------|-------------|
| Conceptual Understanding | 40%    | CU   | 0 / 0.5 / 1 |
| Approach & Method        | 20%    | AM   | 0 / 0.5 / 1 |
| Step-by-Step Execution   | 20%    | SS   | 0 / 0.5 / 1 |
| Numerical Accuracy       | 10%    | NA   | 0 / 0.5 / 1 |
| Presentation & Clarity   | 10%    | PR   | 0 / 0.5 / 1 |

`Q = 0.40·CU + 0.20·AM + 0.20·SS + 0.10·NA + 0.10·PR ∈ [0, 1]` per question.

## Performance Bands

| Band              | Range   | Color  | Action |
|-------------------|---------|--------|--------|
| Trailblazer       | ≥ 75%   | Green  | Promotes to next tier |
| Qualifier         | 60–74%  | Blue   | Promotes from WA → QA; retake at QA level |
| Developing        | 45–59%  | Amber  | Targeted revision before retake |
| Foundational Gaps | < 45%   | Red    | Foundational rebuild required |

Promotion thresholds: **WA ≥ 60% → QA**, **QA ≥ 75% → AA**. AA is the top tier.
ZA (Quiz Assignments) bypass this pipeline and are scored via Google Forms.

## Report Structure

The generated PDF (`{StudentName}_{Code}_{YYYY-MM-DD}_Report.pdf`) contains:

| Page(s) | Section |
|---|---|
| 1 | Cover — student strip + headline score block + status/promotion bar + plain-language summary box + rubric breakdown (5-axis snowflake + 5-row table) |
| 2 | Concept Dependency Map → Misconceptions (conditional) → SWOT Matrix |
| 3 | Areas of Improvement (3 priorities: Critical / Important / Nice-to-have) |
| 4+ | Per-Question cards (function fade gradient, your-vs-expected answer, 5 dimension tiles, feedback paragraph, scan note) |
| Last | Closing note + disclaimer + signature + tracking ID with QR code → Scan quality overview |

## Outputs

- **`{name}_{code}_{date}_Report.pdf`** in Drive `reports/` folder
- **`scores.csv`** in Drive `reports/` folder — append-only log with all rubric dimensions
- **`.tmp/reports/`** — local PDF cache (regenerable)
- **`.tmp/last_eval.json`** — most recent evaluation JSON (useful for re-rendering without re-calling Claude)

## Re-rendering Without Re-evaluating

If you tweak the LaTeX template and want to refresh a single report without spending tokens:

```bash
python3 -c "
import sys, os, json; sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv('.env')
from tools.generate_report import generate
from tools.upload_report import upload
ev = json.load(open('.tmp/last_eval.json'))
pdf = generate(ev)
upload(pdf, os.getenv('DRIVE_REPORTS_ID').strip())
"
```

## Error Handling

| Error | Behaviour |
|-------|-----------|
| Answer key not found in Drive | Logs `SKIPPED — Answer key '...' not found.` and continues |
| Answer key not yet APPROVED | Logs `⏸ SKIP (key not approved)` and continues |
| Student submitted no PDF | Skipped silently (no Drive attachment found) |
| Claude API error | Logs error, skips this submission, retries next tick |
| Tectonic compile failure | Raises with last 4000 chars of `.log` for debugging |
| Drive upload failure | Logs error; local PDF remains in `.tmp/reports/` |

## Updating This Workflow

Edit this file when you encounter:
- New rate-limit / quota errors and the workaround
- Changes to Google Classroom API behaviour
- Subject-specific scoring adjustments (when we extend beyond Mathematics)
- Edge cases in handwriting recognition for new topic types
