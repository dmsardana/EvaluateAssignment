# EvaluateAssignment Framework - Changelog

Version history of the framework. Every meaningful design decision is logged here.

---

## v1.0 - May 2026 (Current)

**Status:** Production. Used for Kiran Vinu Niar's WA-DOM2 evaluation (gold standard reference).

### Locked-in rubric

- **Standard Subjective Rubric** with 5 dimensions: Conceptual Understanding (40%), Approach & Method (20%), Step-by-Step Execution (20%), Numerical Accuracy (10%), Presentation & Clarity (10%)
- Sub-scores 0 / 0.5 / 1 per dimension
- Per-question score formula: Q = 0.40*CU + 0.20*AM + 0.20*SS + 0.10*NA + 0.10*PR

### Locked-in tier system

- **WA** (Warm-Up Assignment) - Subjective - >=60% promotes to QA
- **ZA** (Quiz) - Objective auto-graded - NOT evaluated by Claude
- **QA** (Qualifier's Assignment) - Subjective - >=75% promotes to AA
- **AA** (Achiever's Assignment) - Subjective - >=75% confirms mastery

No leapfrogging. A student scoring 95% on WA still goes to QA next.

### Locked-in performance bands

| Band | Range | Color |
|---|---|---|
| Trailblazer | >= 75% | tsGreen (#2E8540) |
| Qualifier | 60-74% | tsBlue (#0066CC) |
| Developing | 45-59% | tsAmber (#D97706) |
| Foundational Gaps | < 45% | tsRed (#C8102E) |

### Locked-in report structure

| Page | Section |
|---|---|
| 1 | Header + Student block + Score block + Promotion bar + Summary Box + Rubric Breakdown (snowflake + table) + score formula |
| 2 | Concept Dependency Map (always starts fresh on page 2) |
| 2 or 3 | SWOT Matrix (fits on page 2 if room, else fresh page) |
| 3 or 4 | Areas of Improvement (always fresh page) |
| 5+ | Per-Question Evaluation (always fresh page) |
| -2 | Closing Note + Where to go next + Disclaimer + Signature + Tracking ID + QR code |
| -1 | Scan Quality Overview + Scanning Tips appendix |

### Locked-in macro vocabulary

`ts_evalreport.sty` includes:

- **Page-1 hero:** `\tsStudentBlock`, `\tsScoreBlock`, `\tsPromotionBar`, `\tsSummaryBox`
- **Headings:** `\tsHone`, `\tsHtwo`, `\tsHthree`, `\tsHfour`
- **Rubric breakdown:** `tsRubricSplit` env (snowflake + 5-row table side-by-side)
- **Concept map:** `tsConceptMap` env, `\tsConceptMapHeader`, `\tsConceptRow`, cell shortcuts `\tsCG/\tsCA/\tsCR/\tsCN`, header cell helper `\tsCH`
- **Coaching sections:**
  - `tsMisconceptions` env + `\tsMisconception` (CONDITIONAL - omit if no patterns)
  - `\tsSWOT` (always 4-quadrant grid) with `\tsSWOTpoint`
  - `tsImprovements` env + `\tsImprove` (always 3 priorities) - bold editorial design with oversized 01/02/03 numerals
- **Per-question card:** `tsQCard` env with auto-fade gradient on `\tsQFunc`
- **Closing:** `\tsDisclaimer`, `\tsSignature`, `\tsTrackingBlock` (ID + QR code, no visible URL)
- **Scan tips:** `tsScanTips` env + `\tsTip`

### Locked-in build chain

- xelatex (required for unicode-math + fontspec)
- TeX Gyre Heros for body, Latin Modern Math for math mode
- A4 paper, 2cm margins all sides, 17cm content width, 2.8cm header band
- Logo: 680x680 transparent RGBA PNG, rendered at 2cm width in header

### Locked-in output naming

- Filename: `<StudentName>_<AssignmentCode>_<YYYY-MM-DD>_Report.{tex,pdf}`
- Tracking ID: `TS-{tier}-{assignment}-{YYYYMMDD}-{studentInitials}-{seqNum}`
  - Example: `TS-WA-DOM2-20260509-KVN-001`
- QR code encodes: `https://thinkingsouls.com/track/{TrackingID}` (placeholder URL for future dashboard)

---

## Pending / Open items

- None at the moment. Framework is stable.

## Deprecated / Removed

### Pattern Diagnosis (deprecated April 2026)

The original "Pattern Diagnosis" section (Strengths bullets + Developmental Nudges) has been replaced by the three-section coaching structure: Misconceptions (conditional) -> SWOT Matrix -> Areas of Improvement. Do not use `\tsHone{Pattern Diagnosis}` in new reports.

### Achiever (band name, deprecated May 2026)

The >=75% band was originally called "Achiever" - this conflicted with "Achiever's Assignment" (AA tier). Renamed to **Trailblazer** to remove the overlap. The AA tier name is unchanged (still "Achiever's Assignment", since AA = the original acronym).

### Visible URL on Tracking Block (deprecated May 2026)

The tracking block originally rendered the URL as visible text below the box. Now the URL is encoded ONLY into the QR code; only the human-readable Tracking ID is shown.

### Scan Quality Overview on page 1 (deprecated May 2026)

Originally rendered as `\tsHtwo{Scan Quality Overview}` near the top of page 1. Moved to its own appendix page at the end of the report (right before the Scanning Tips grid).

---

## Reference example

See `examples/Kiran_DOM2_WA_Report.{tex,pdf}` for the gold-standard reference. This is a 100% scorer (all 25 questions correct), so the Misconceptions section is omitted (correctly - that section is conditional). Other features all visible: Summary Box, Concept Map heat-map, SWOT Matrix, Areas of Improvement (priority 01/02/03 cards), per-question cards with fade gradient, Tracking ID + QR code on closing page.
