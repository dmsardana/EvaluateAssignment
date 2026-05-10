# RUNBOOK — Assignment Evaluation Pipeline

How to operate the system day-to-day. For setup details, see `workflows/setup.md`.

---

## What this system does

```
You post an assignment in Google Classroom
        ↓
System detects it, generates an answer key with Claude (Opus 4.7 for QA/AA, Sonnet 4.6 for WA)
        ↓
You receive an email with the AK PDF + a 6-character OTP
        ↓
You reply "OK <OTP>" to approve, or "Q3, Q5-7 reprocess <OTP>" to flag specific Qs for redo
        ↓
Once approved, every student submission gets graded against that key
        ↓
Each student gets a multi-page PDF report uploaded to Drive `reports/`
        ↓
scores.csv on Drive logs every score with progression eligibility flags
```

End result: **one PDF report per student, automatically graded against an AI-generated, teacher-approved answer key, with rubric-based scoring + qualitative feedback + concept dependency map + SWOT + improvement priorities.**

---

## Begin (one command)

```bash
python3 tools/run_pipeline.py
```

That's it. The pipeline polls Google Classroom every `POLL_INTERVAL_SECONDS` (default 60s) and does everything described above. Press `Ctrl+C` to stop.

For a one-shot run (process everything pending right now and exit):

```bash
python3 tools/run_pipeline.py --once
```

---

## What you'll see in your inbox

For every new coursework detected:

> **Subject:** [ACTION] Approve Answer Key: QA DOM3 — OTP: AB12CD
>
> Assignment: 07 Domain | Code: DOM3 | Type: QA
> Type: QA | Code: DOM3 | Questions: 8 | Model: claude-opus-4-7
>
> **Approval OTP:** AB12CD
>
> All approved → reply: `OK AB12CD`
> Reprocess specific → reply: `Q3, Q5-7 reprocess AB12CD`
>
> [QA_DOM3_KEY.pdf attached]

The PDF has two sections: **§1 Concise Solution Set** (final answers + key steps) and **§2 Detailed Solutions** (full step-by-step working).

### How to reply

| If… | Reply |
|---|---|
| Every question is right | `OK AB12CD` |
| A few questions are wrong | `Q3, Q7 reprocess AB12CD` |
| A range is wrong | `Q5-9 reprocess AB12CD` |
| Whole thing is wrong | `Wrong, redo all AB12CD` (or just `Redo all AB12CD`) |

The parser strips the original quoted email body, so even if your reply is just two words above the quote it'll work.

---

## End result

For every student submission graded:

1. **PDF report** uploaded to Drive `reports/` folder. Filename: `StudentName_CODE_YYYY-MM-DD_Report.pdf`
2. **scores.csv** appended on Drive — full rubric breakdown per student
3. **Progression flag** auto-computed: ≥60% on WA → qualifies for QA; ≥75% on QA → qualifies for AA

The PDF is multi-page:

- **Cover** — student strip (with vertical rules), 42pt headline score, color-coded performance band, status/promotion bar, plain-language summary box, 5-axis snowflake chart + rubric table
- **Page 2** — Concept Dependency Map (heat-map of concepts × questions), Misconceptions Identified (only if 2+ Qs share an error), 2×2 SWOT Matrix
- **Page 3** — Areas of Improvement (3 priorities: Critical / Important / Nice-to-have, editorial-style cards)
- **Pages 4+** — Per-question evaluation cards (function with fade gradient, your-vs-expected answer, 5 dimension tiles, written feedback, scan note if applicable)
- **Closing page** — motivational closing note + disclaimer + signature + tracking ID + QR code

---

## Day-to-day commands

| Need to… | Run |
|---|---|
| Start the pipeline | `python3 tools/run_pipeline.py` |
| Process pending and stop | `python3 tools/run_pipeline.py --once` |
| Check what submissions are pending | `python3 tools/watch_classroom.py` |
| Manually check email replies | `python3 tools/check_review_replies.py` |
| Generate AK for one specific coursework | `python3 tools/generate_answer_key.py <coursework_id>` |
| Re-do flagged questions in an existing key | `python3 tools/generate_answer_key.py --regen <coursework_id>` |
| Re-render a report without re-evaluating | See `workflows/evaluate_assignment.md` § Re-rendering |

---

## Common gotchas

- **"Access blocked: app has not completed Google verification"** — your account isn't a test user. Add yourself in Google Cloud Console → OAuth consent screen → Audience tab → Test users.
- **"Not all requested scopes were granted"** — delete `token.json` and re-run `setup_drive.py`. Tick every checkbox during the consent flow.
- **Answer key not matching** — your assignment title must contain a parsable code. See `workflows/setup.md` § Step 4.
- **Report PDF looks broken** — check that `tectonic` is the path in `.env` `PDFLATEX_PATH`. Bundled fonts (`*.otf`) must be in `tools/templates/`.
- **Email reply not picked up** — wait one polling cycle (default 60s), or run `python3 tools/check_review_replies.py` directly. Reply must come from `TEACHER_EMAIL`.

---

## Where things live

```
EvaluateAssignment/
├── tools/                         # Python scripts (run individually or via run_pipeline.py)
│   ├── setup_drive.py             # one-time OAuth + folder discovery
│   ├── run_pipeline.py            # main orchestrator (this is what you run)
│   ├── watch_classroom.py         # lists pending submissions
│   ├── download_pdf.py            # fetches submission + answer key
│   ├── generate_answer_key.py     # AK generation + email send
│   ├── check_review_replies.py    # Gmail polling + reply parser + auto-regen
│   ├── evaluate_pdf.py            # Claude vision evaluation
│   ├── generate_report.py         # LaTeX render + tectonic compile
│   ├── upload_report.py           # uploads PDF to Drive
│   ├── track_scores.py            # appends to scores.csv
│   ├── email_helper.py            # Gmail send/read shared helpers
│   ├── review_state.py            # Drive-stored state JSON
│   └── templates/
│       ├── ts_evalreport.sty      # ThinkingSouls report style package
│       ├── report_template.tex    # student report Jinja template
│       ├── answer_key_template.tex # answer key Jinja template
│       ├── logo.png
│       ├── texgyreheros-*.otf     # bundled body fonts
│       └── latinmodern-math.otf   # bundled math font
├── workflows/                     # operational SOPs
│   ├── setup.md
│   ├── generate_answer_key.md
│   └── evaluate_assignment.md
├── references/                    # design exemplars + the .sty source of truth
├── .tmp/                          # disposable cache (regenerable)
├── .env                           # API keys + folder IDs (gitignored)
├── .env.example                   # template for .env
├── credentials.json               # Google OAuth client (gitignored)
├── token.json                     # Google OAuth token (gitignored)
├── tectonic                       # LaTeX engine binary
└── requirements.txt
```

Cloud-side, in your Drive root folder:

```
EvaluateAssignment/
├── answer_keys/
│   ├── WA_DOM2_KEY.pdf
│   ├── QA_DOM3_KEY.pdf
│   └── answer_key_state.json    # state machine for review workflow
└── reports/
    ├── ChaitanyaaPandey_DOM3_2026-05-10_Report.pdf
    ├── ...
    └── scores.csv               # cumulative scoring log
```

---

## When something looks wrong

1. Check the latest line in stderr from `run_pipeline.py` — every step logs.
2. The local PDF cache in `.tmp/reports/` is preserved — if Drive upload failed, your file is still there.
3. The local evaluation JSON cache in `.tmp/last_eval.json` lets you re-render without spending tokens.
4. State for AK approval lives at `answer_keys/answer_key_state.json` on Drive — open it in a JSON viewer to debug.

---

## Cost expectations

For a single QA assignment with 25 questions × 10 students:

| Step | Calls | Approx cost |
|---|---|---|
| Answer key generation (Opus 4.7) | 1 | $0.50–$1.00 |
| Per-student evaluation (Opus 4.7) | 10 | ~$3–$5 |
| **Total per QA assignment** | | **~$3.50–$6** |

WA (Sonnet 4.6) is roughly 5× cheaper. Re-runs (e.g. after a "redo all" reply) charge again.
