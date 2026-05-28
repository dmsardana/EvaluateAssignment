# Student Evaluation Report — Structure & Architecture

> Single reference for the evaluation-report PDF: what is rendered,
> what data drives it, and which file produces each piece. Pair with
> [CLAUDE.md](../../CLAUDE.md) for the wider pipeline.

---

## 1. Pipeline overview

```
Student PDF (Drive)            Answer Key PDF (Drive)
       |                                |
       +---------------+----------------+
                       |
                       v
        tools/evaluate_pdf.py  -->  Anthropic Files API + Claude vision
                       |                (or Gemini / OpenAI)
                       v
            evaluation JSON  -->  .tmp/evaluations/<cwid>_<sid>.json
                       |              (cache - re-eval skips the LLM)
                       v
        tools/generate_report.py  -->  Jinja2 -> report_template.tex
                       |                       + ts_evalreport.sty
                       v
                    tectonic
                       |
                       v
        .tmp/reports/<Name>_<Code>_<Date>_Report.pdf  -->  Drive `reports/`
```

Three concerns kept strictly separated:

| Concern | File / dir | Owner |
|---|---|---|
| **What** to grade + how | `tools/evaluate_pdf.py` (prompt + parse) | Claude vision |
| **How** to lay it out | `tools/templates/report_template.tex` | Jinja |
| **How** it looks | `tools/templates/ts_evalreport.sty` | LaTeX macros |

---

## 2. Evaluation JSON schema (the contract)

Every component below maps to a key in this JSON. Persisted at
`.tmp/evaluations/<cwid>_<sid>.json`.

```jsonc
{
  "student":     { "name": "...", "id": "..." },
  "assignment":  { "type": "QA", "code": "DOM1", "title": "...",
                   "topic": "Domain", "topic_breadcrumb": "Maths > ..." },
  "evaluation_date":         "2026-05-27",
  "paper_total_questions":   15,                // see padding rule (sect 7)

  "summary": {
    "total_questions":     15,                   // paper total
    "attempted_questions": 12,                   // attempted only
    "earned_score":        9.3,
    "max_score":           15.0,                 // == total_questions
    "percentage":          62.0,
    "band":         "Qualifier",
    "band_color":   "tsAmber",
    "verdict":      "Qualifies for AA",
    "promotion_text": "Promoted to AA.",
    "promotion_note": "Threshold (>=60%) cleared by 2.0 pp.",
    "qualifies_for":  "AA",                       // null if none
    "summary_box":    "3-4 sentence plain summary.",
    "scan_quality_breakdown": {"Excellent":3,"Good":10,"Acceptable":2,"Poor":0},
    "scan_quality_note": "..."
  },

  "rubric_aggregate": {
    "concept_understanding_pct": 71,
    "approach_method_pct":       65,
    "step_by_step_pct":          59,
    "numerical_accuracy_pct":    60,
    "presentation_pct":          78
  },

  "concept_map": {
    "concepts": ["Square root non-negativity", "Log positivity", "..."],
    "matrix":   [ ["G","G","A","R","N", "..."],  // one row per concept
                  "..." ]                         // each row length == paper_total_questions
  },

  "swot":           { "strengths": [], "weaknesses": [],
                      "opportunities": [], "threats": [] },
  "misconceptions": [{ "title": "", "evidence": "",
                       "wrong_model": "", "correct_model": "" }],
  "improvements":   [{ "priority": 1, "label": "Critical", "color": "tsRed",
                       "title": "", "action": "",
                       "measure": "", "by_when": "" }],   // exactly 3
  "closing_note":   { "intro": "", "what_signals": "",
                      "next_steps": [
                        { "label": "Focus topic",    "text": "..." },
                        { "label": "Adjacent topic", "text": "..." },
                        { "label": "Speed target",   "text": "..." }
                      ] },

  "questions": [
    { "number": 1, "topic": "", "function_latex": "",
      "your_answer": "", "expected_answer": "",
      "dimensions": {
        "concept_understanding": {"score": 0.78, "comment": "..."},
        "approach_method":       {"score": 0.62, "comment": "..."},
        "step_by_step":          {"score": 0.55, "comment": "..."},
        "numerical_accuracy":    {"score": 1.00, "comment": "..."},
        "presentation":          {"score": 0.80, "comment": "..."}
      },
      "weighted_score": 0.71,                    // recomputed server-side
      "feedback":     "...",
      "scan_quality": "Good",
      "scan_note":    ""
    }
  ],

  "usage": {                                      // see sect 8
    "provider": "anthropic", "model": "claude-sonnet-4-6",
    "input_tokens": 14523, "output_tokens": 11201,
    "cost_usd_est": 0.211,
    "submission_kb": 2620.3, "answer_key_kb": 78.4,
    "calls": [ { "...per-call including self-heal retries": "" } ]
  },

  "tracking_id": "QA-DOM1-Adithya-2026-05-27"
}
```

**Per-question weighting** (re-applied server-side):

```
weighted_score = 0.40 * CU  +  0.20 * AM  +  0.20 * SS
                +  0.10 * NA  +  0.10 * PR        in [0, 1]
```

---

## 3. Report components (page-by-page inventory)

Numbers match the visual order in the PDF.

### Page 1 - Summary

| # | Component | Source JSON | Template | Style macro | Conditional? |
|---|---|---|---|---|---|
| 1 | **Header band** (topic breadcrumb + tier) | `assignment.topic_breadcrumb`, `assignment.type` | `report_template.tex:65` | `\tsSetHeader` / `\tsSetTier` | Always |
| 2 | **Student Block** (Name / Assignment / Topic / Date) | `student.name`, `assignment.code/title/topic`, `evaluation_date_human` | `:75` | `\tsStudentBlock` (overridden in template head, see `:11-39`) | Always |
| 3 | **Score Block** (percentage / earned-of-max / band / verdict) | `summary.percentage`, `summary.earned_score`, `summary.max_score`, `summary.band`, `summary.band_color`, `summary.verdict` | `:77` | `\tsScoreBlock` | Always |
| 4 | **Attempted-vs-Total note** | `summary.attempted_questions`, `summary.total_questions`, `summary.earned_score` | `:79-82` | inline italic | **Only when** `attempted < total` |
| 5 | **Promotion / Status bar** | `summary.promotion_text`, `summary.promotion_note`, `summary.qualifies_for`, `summary.band_color` | `:84-88` | `\tsPromotionBar` | Two variants: PROMOTION (green bg) if `qualifies_for` set, else STATUS (light bg) |
| 6 | **Summary Box** | `summary.summary_box` | `:90` | `\tsSummaryBox` | Always |
| 7 | **Rubric Breakdown** (5-dim split-bar + table) | `rubric_aggregate.{cu,am,ss,na,pr}_pct` | `:92-100` | `\tsRubricSplit` + `\rubricRowC` x 5 | Always; weights hard-coded 40/20/20/10/10 |

Page 1 is the executive view — score, band, promotion outcome, and the
single-paragraph "what happened" summary. Operators glance here first.

### Page 2+ - Diagnostic layers

| # | Component | Source JSON | Template | Style macro / structure | Conditional? |
|---|---|---|---|---|---|
| 8 | **Concept Dependency Map** (heat-map: concepts x questions) | `concept_map.concepts[]`, `concept_map.matrix[][]` | `:108-118` | `\tsConceptMap` env + `\tsConceptRow` + cells `\tsCG / \tsCA / \tsCR / \tsCN` | Only when both `concepts` and `matrix` non-empty. **Chunked into blocks of 25 questions** - see sect 4 |
| 9 | **Summary of Rubric Matrix** (per-Q x 5 dims + average) | `questions[].dimensions.*.score`, `questions[].avg_pct` (computed in `generate_report.py:276-302`) | `:137-180` | `longtable` with repeating `\endhead` | Always; sorted by `avg_pct` descending so weakest rows surface first |
| 10 | **Misconceptual Observations Identified** | `misconceptions[]` (title, evidence, wrong_model, correct_model) | `:194-201` | inline 2-col tabular | Only when `misconceptions` non-empty |
| 11 | **SWOT Matrix** | `swot.{strengths,weaknesses,opportunities,threats}[]` | `:209-232` | 2 x 2 grid via SWOT cells | Always |
| 12 | **Areas of Improvement** (Critical / Important / Nice-to-have) | `improvements[].{priority,label,color,title,action,measure,by_when}` | `:240-251` | improvement-card layout | Always; **exactly 3** entries enforced by prompt |
| 13 | **Per-Question Evaluation** (one card per question) | `questions[]` (full shape) | `:258-274` | per-question tcolorbox + answer rows + 5 dim cells + feedback box | Always; sorted **ascending** by `q.number` |
| 14 | **Closing Note** (intro / what_signals / next_steps[3]) | `closing_note.{intro,what_signals,next_steps}` | `:282-307` | closing box + next-step rows | Always |
| 15 | **Scan Quality Overview** | `summary.scan_quality_breakdown`, `summary.total_questions` | `:314-319` | inline coloured chips | Always |
| 16 | **Scanning Tips for Future Submissions** | static list (no data binding) | `:322` | `\tsScanningTips` | Always |
| -- | **Page footer** (every page) | `student.name`, `assignment.type/code/topic`, `evaluation_date_human` | `:67` | `\tsSetFooter` | Always |

---

## 4. Chunking & overflow rules

| Component | Rule | Why |
|---|---|---|
| Concept Dependency Map | Split into blocks of **25 questions** per `tsConceptMap` env; blocks emitted by `make_concept_map_helpers` in `generate_report.py:120-159` | A single tabular with 40+ columns overflows the page |
| Summary of Rubric Matrix | `longtable` with header row repeated via `\endhead` (`report_template.tex:152-168`) | Tables longer than one page need their header on each break |
| Per-Question Evaluation | Each question is a self-contained `tcolorbox` so LaTeX can page-break between cards | Avoid mid-card breaks |

---

## 5. Style system - `ts_evalreport.sty`

Public macros the template (and future variants) may call:

| Macro | Purpose |
|---|---|
| `\tsHone{title}` | Section heading |
| `\tsStudentBlock{name}{assignment}{topic}{date}` | Page-1 student banner |
| `\tsScoreBlock{pct}{earned}{max}{band}{color}{verdict}` | Big score panel |
| `\tsPromotionBar{barColor}{bgColor}{label}{textColor}{text}{note}` | Promotion / Status bar |
| `\tsSummaryBox{text}` | Plain-language summary box |
| `\tsRubricSplit{cu}{am}{ss}{na}{pr}` env | Split-bar + 5-row rubric table |
| `\rubricRowC{label}{weight}{score}{status-pill}` | One row inside `tsRubricSplit` |
| `\tsConceptMap{N}` env | N-column concept heat-map |
| `\tsConceptMapHeader{cells}` / `\tsConceptRow{label}{cells}` | Heat-map header + row |
| `\tsCG / \tsCA / \tsCR / \tsCN` | Heat-map cells: full / partial / failed / not-tested |
| `\tsScanningTips` env | Static-tips block |

**Colour tokens**: `tsGreen, tsAmber, tsRed, tsBlue, tsGrey, tsText, tsLightGrey, tsBgGreen, tsBgLight, conciseGreen, headerBlue, boxBg`.

**Fonts**: TeX Gyre Heros (sans) + Latin Modern Math, bundled at
`tools/templates/*.otf`. tectonic resolves them at compile time.

---

## 6. Defensive filters (sanitisers)

The model emits raw LaTeX inside JSON strings. Filters keep the
renderer from crashing on model misbehaviour:

| Filter | Applied to | What it does |
|---|---|---|
| `latex_escape` | `assignment.title`, `q.difficulty`, `common_mistakes`, headers — text-only fields | Escapes `& % # _` (LaTeX special chars) |
| `latex_sanitize` | `question_text, approach, solution, concise, final_answer` — math-bearing fields | (a) literal `\n / \t / \r` -> real whitespace, (b) unicode math (`x^2`, arrow, leq, alpha, ...) -> LaTeX `$...$`, (c) **balances stray `$`** by appending closing `$` if count is odd |

Plus question-field defaults in
`generate_report.py:questions_for_template` — every per-question dict
has `topic, function_latex, your_answer, expected_answer, feedback,
scan_quality, scan_note` filled with safe defaults so Jinja's
`StrictUndefined` cannot throw on a missing field from an older cached
eval.

And the self-healing LaTeX retry loop in
`tools/generate_answer_key.py:process_coursework` — if compile fails,
send the LaTeX error + the bad JSON back to the model, regenerate just
the affected fields, retry. Up to 2 fix-ups (3 total compile attempts).

---

## 7. Padding & normalisation (paper_total vs attempted)

`evaluate_pdf.py:_normalize_concept_map` + the post-parse block ensure:

- **`paper_total_questions`** is set (from model field, else max
  `q.number`, else `len(questions)`).
- Every concept-map row is padded with `"N"` to length
  `paper_total_questions` (model often emits short rows).
- Missing per-question entries are synthesised with `score=0` and
  `comment="Not attempted"` so the per-question section + denominator
  always reflect the **paper**, not just attempted work.
- `summary.attempted_questions` counts entries with `weighted_score > 0`
  OR `feedback != "Not attempted"`.
- Percentage = `earned / paper_total * 100`. The
  attempted-vs-total note (component #4) surfaces when these differ.

This prevents the 29-of-40 = 94% inflation bug.

---

## 8. Cost & usage tracking

Every LLM call routes through **`tools/usage_log.py:log_llm_call`**.
One JSONL line is appended per call at
`.tmp/_usage/YYYY-MM-DD.jsonl`, with a per-evaluation roll-up attached
to `evaluation.usage` (see sect 2 schema).

Tracked sites:

| Call site | `purpose` |
|---|---|
| `evaluate_pdf.py:_call_anthropic_vision` | `evaluation` |
| `evaluate_pdf.py:_call_gemini_vision`    | `evaluation` |
| `evaluate_pdf.py:_call_openai_vision`    | `evaluation` |
| `generate_answer_key.py:generate_solutions` | `ak_generation` |
| `generate_answer_key.py:_fix_solutions_for_latex` | `ak_self_heal` |

Daily roll-ups:

```bash
# total spend today
jq -s 'map(.cost_usd_est) | add' .tmp/_usage/$(date -u +%F).jsonl

# spend by purpose
jq -r '"\(.purpose)\t\(.cost_usd_est)"' .tmp/_usage/$(date -u +%F).jsonl \
  | awk '{s[$1]+=$2} END {for(k in s) printf "%-20s $%.3f\n", k, s[k]}'

# top spenders
jq -r '[.student_name // "ak", .assignment_code // "-", .purpose, .cost_usd_est] | @tsv' \
  .tmp/_usage/$(date -u +%F).jsonl | sort -k4 -rn | head -10
```

To add a new provider/model: append a row to `PRICES_PER_M` in
`tools/usage_log.py`. Nothing else changes.

---

## 9. Extending the report

| Want to ... | Touch |
|---|---|
| Add a new section | Declare context var in `generate_report.py:generate` -> add block in `report_template.tex` -> (optionally) add `.sty` macro |
| Compact variant (Page 1 + Concept Map + Closing Note only) | Branch on a `variant` flag in the template; components #8 + #14 + Page 1 are the only ones needed. Saves ~70% output tokens. |
| Add a new tier (e.g. GA, ZA) | `tools/tier_config.py` is the single source of truth - every consumer reads `KNOWN_TIERS` / `TIER_CONFIG` |
| Tweak a rubric weight | `evaluate_pdf.py:compute_weighted_score` + Rubric Breakdown table in template (display) |

---

## 10. Verification & operations

- **Re-render a cached eval** (no LLM cost):
  ```bash
  python3 -c "import json, sys; from tools.generate_report import generate; \
    print(generate(json.load(open(sys.argv[1]))))" \
    .tmp/evaluations/<cwid>_<sid>.json
  ```
- **Inspect a failed LaTeX compile**: persisted at
  `.tmp/_failed_ak/<ts>_<base>.{tex,log}`. The error message in the UI
  also includes the path.
- **Smoke test the whole flow**: `python3 tools/run_pipeline.py --once`
  (see [RUNBOOK.md](../../RUNBOOK.md)).

---

## Source files (for deeper reading)

| File | What is in it |
|---|---|
| [tools/evaluate_pdf.py](../../tools/evaluate_pdf.py) | Vision-LLM call, prompt schema, JSON parse + normalise, cost log |
| [tools/generate_report.py](../../tools/generate_report.py) | Jinja env, context build, concept-map blocking, tectonic invoke |
| [tools/templates/report_template.tex](../../tools/templates/report_template.tex) | The component layout |
| [tools/templates/ts_evalreport.sty](../../tools/templates/ts_evalreport.sty) | Macros, colours, fonts |
| [tools/usage_log.py](../../tools/usage_log.py) | Shared LLM cost logger |
| [tools/tier_config.py](../../tools/tier_config.py) | WA / QA / AA / GA / ZA tier rules |
| [CLAUDE.md](../../CLAUDE.md) | Project-wide pipeline overview |
| [RUNBOOK.md](../../RUNBOOK.md) | Day-to-day operations |
