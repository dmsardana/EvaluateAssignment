# EvaluateAssignment - Claude Project Kit

**ThinkingSouls Mathematics evaluation framework for JEE coaching.** This kit lets Claude evaluate student assignment scans and produce branded multi-page LaTeX reports with consistent rubric scoring, coaching analysis, and a professional aesthetic.

---

## What this is

A complete project knowledge bundle for the `EvaluateAssignment` Claude Project. Drop the contents into a Claude Project's knowledge base (or attach as files to a single conversation) and Claude can:

- Score subjective math assignments using the **Standard Subjective Rubric** (CU/AM/SS/NA/PR, weighted 40/20/20/10/10)
- Determine the band (Trailblazer / Qualifier / Developing / Foundational Gaps)
- Determine tier promotion (WA -> QA -> AA, with no leapfrogging)
- Generate a complete TEX bundle that compiles to a 14-15 page branded PDF report with:
  - Score block + promotion bar + plain-language Summary Box
  - Rubric breakdown (snowflake chart + weighted table)
  - Concept Dependency Map (heat-map of which concepts each Q tests)
  - SWOT Matrix (4-quadrant strategic picture)
  - Areas of Improvement (3 priorities with bold editorial design)
  - Per-question evaluation cards (5 dimension tiles + feedback + privacy fade on question text)
  - Closing note + Where to go next + AI disclaimer + signature
  - Tracking ID + scannable QR code (for future dashboard linkage)
  - Scan Quality Overview + Scanning Tips appendix

The framework is subject-agnostic but currently tuned for JEE Mathematics (Differential Calculus / Functions / Domain). Easy to extend to Physics, Chemistry, or other Math topics by adjusting concept lists.

---

## File map

| File | Purpose | When to read |
|---|---|---|
| **README.md** (this file) | Project overview + onboarding | Start here |
| **0_PROJECT_INSTRUCTIONS.md** | Custom instructions for the Claude Project | Paste into project's "Instructions" field |
| **1_HOW_TO_USE.md** | Operator-facing process guide | Every time you run a new evaluation |
| **2_FRAMEWORK_REFERENCE.md** | Locked rubric, tier system, all section definitions | When deciding how to score / structure |
| **3_SAMPLE_PROMPTS.md** | Common prompts for mid-evaluation corrections | When you need to adjust an output |
| **4_QUALITY_CHECKLIST.md** | Pre-delivery validation checklist | Before sending the report to the student |
| **scoring_rubric_quickref.md** | One-page cheat sheet | When you need band thresholds in a hurry |
| **CHANGELOG.md** | Version history of framework decisions | When questioning a design choice |
| **logo.png** | ThinkingSouls brand logo (transparent PNG) | Project icon / report header |
| **templates/REPORT_TEMPLATE.tex** | Fillable LaTeX skeleton with [PLACEHOLDER]s | Starting point for every new report |
| **templates/README_TEMPLATE.md** | Macro vocabulary reference for the STY | When writing custom TEX content |
| **templates/ts_evalreport.sty** | Locked LaTeX style file (do not modify) | Used by every report |
| **templates/logo.png** | Transparent logo for the report header | Auto-included by the STY |
| **examples/Kiran_DOM2_WA_Report.tex** | Gold-standard reference example (TEX) | Pattern to copy for new reports |
| **examples/Kiran_DOM2_WA_Report.pdf** | Gold-standard reference example (PDF) | Visual reference of final output |

---

## Quick start (first evaluation)

1. **Set up the Project**
   - Create a Claude Project named `EvaluateAssignment` (or similar)
   - Copy the contents of `0_PROJECT_INSTRUCTIONS.md` into the project's "Instructions" field
   - Upload all files in this bundle to the project's knowledge base
   - Optional: set the project icon to `logo.png`

2. **Run an evaluation**
   - Open a new conversation in the project
   - Upload the student's scanned assignment PDF
   - Send a one-line prompt: `Evaluate this submission. Student: <name>. Assignment: <code>. Topic: <topic>.`
   - Claude reads the framework, applies the rubric question-by-question, and produces:
     - An in-chat per-question grading table
     - A complete TEX bundle as files (`<student>_<code>_<date>_Report.tex` + compiled PDF + STY + logo)

3. **Review and adjust**
   - Check the in-chat output against the rubric
   - Use prompts from `3_SAMPLE_PROMPTS.md` to override specific scores or coaching content
   - Verify with `4_QUALITY_CHECKLIST.md` before delivering

4. **Deliver**
   - Send the PDF to the student / parent
   - Quote the tracking ID (`TS-WA-DOM2-...`) in any follow-up communication

---

## Locked decisions

These are settled. Do not relitigate without explicit conversation.

- **Rubric weights:** CU 40%, AM 20%, SS 20%, NA 10%, PR 10%
- **Sub-scores:** 0, 0.5, or 1 per dimension per question
- **Bands:** Trailblazer (>=75%), Qualifier (60-74%), Developing (45-59%), Foundational Gaps (<45%)
- **Tiers:** WA -> ZA (skipped) -> QA -> AA. No leapfrogging. ZA is auto-graded, not Claude-evaluated.
- **Engine:** xelatex with unicode-math and TeX Gyre Heros body / Latin Modern Math
- **Geometry:** A4, 2cm margins, 17cm content width, 2.8cm header band
- **Brand colors:** tsRed (#C8102E), tsGreen (#2E8540), tsBlue (#0066CC), tsAmber (#D97706), tsText (#1A1A1A)
- **Output filename:** `<StudentName>_<AssignmentCode>_<YYYY-MM-DD>_Report.{tex,pdf}`
- **Tracking ID format:** `TS-{tier}-{assignment}-{YYYYMMDD}-{studentInitials}-{seqNum}`
- **Logo:** transparent PNG, used by `ts_evalreport.sty` at 2cm width in the header
- **Summary Box label:** literally "S U M M A R Y" - never "Parent Summary" or any other prefix

---

## Need help?

- For framework questions, see `2_FRAMEWORK_REFERENCE.md`
- For the macro reference, see `templates/README_TEMPLATE.md`
- For prompt patterns, see `3_SAMPLE_PROMPTS.md`
- The example in `examples/Kiran_DOM2_WA_Report.{tex,pdf}` is the canonical reference. When in doubt, copy its structure.

---

*ThinkingSouls Education - Mohit Sardana - admin@thinkingsouls.com*
