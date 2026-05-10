# How to Use - EvaluateAssignment Project

This is the day-to-day guide for evaluating a student assignment using Claude. Read it once end-to-end, then keep it open as a reference.

## What this project does

You upload a scanned PDF of a student's completed assignment, and Claude:

1. Reads every question and the student's working
2. Grades each question on the 5-dimension rubric (CU / AM / SS / NA / PR)
3. Computes the weighted score and the band (Trailblazer, Qualifier, Developing, Foundational Gaps)
4. Identifies patterns - strengths and developmental nudges
5. Produces a polished branded TEX report bundle ready to compile and send to the student

You get two outputs:
- **In-chat:** the per-question grading and the aggregate analysis (so you can review before committing)
- **As files:** a TEX file, the compiled PDF, and a reference to the existing `ts_evalreport.sty` style file

## Before you start - prerequisites

You need these things ready:

1. **The student's submission PDF** - scanned with a scanner app (Adobe Scan / Microsoft Lens / CamScanner), pages in correct order, named clearly: `<BatchName>_<StudentName>_<AssignmentCode>.pdf` (e.g. `SPARK-2027_KiranVinuNiar_DOM2.pdf`).

2. **The original question paper PDF** - so Claude can compare student answers against the actual problems. Without this, Claude has to guess what the questions were.

3. **The expected answers** (optional but recommended) - if you have a master answer key, upload it. If not, Claude solves the questions itself, but then YOU need to spot-check.

4. **Student metadata:**
   - Full name (as you want it on the report)
   - Batch / cohort name (e.g. SPARK-2027)
   - Assignment code (e.g. DOM2, FUN3, INT1)
   - Tier (WA / QA / AA - never ZA, since ZA is auto-graded by Google Forms)
   - Topic name (e.g. "Domain of Functions", "Indefinite Integration")
   - Evaluation date (today, usually)

## The seven-step process

### Step 1 - Open a new chat in the EvaluateAssignment project

Always evaluate inside this project. The custom instructions, framework reference, and templates are loaded automatically. If you start a fresh chat outside the project, Claude will not have the rubric locked in.

### Step 2 - Upload the files

Attach to the chat:
- Student submission PDF (required)
- Question paper PDF (required)
- Answer key PDF (optional)

Use the paperclip icon in Claude's chat input. Do not paste images one at a time - upload the full PDFs.

### Step 3 - Send the kickoff prompt

Use one of the canned prompts from `SAMPLE_PROMPTS.md`. The minimum viable prompt is:

```
Evaluate this submission.

Student: Kiran Vinu Niar
Batch: SPARK-2027
Assignment: DOM2
Tier: WA
Topic: Domain of Functions
Date: 09 May 2026

I am [Mohit / a junior evaluator - pick one].

Files attached: student submission, question paper.
```

If you are a junior evaluator, say so explicitly. Claude will stop after the per-question grading and ask you to confirm scores before generating the TEX bundle.

### Step 4 - Review the in-chat grading

Claude returns a per-question grading table. Read it line by line:

- For each Q, do the sub-scores (CU/AM/SS/NA/PR) match what you'd give?
- Is the scan quality grade right? (Excellent / Good / Acceptable / Poor)
- Is the brief feedback specific and accurate?
- Is the overall percentage and band correct?

If anything is off, tell Claude in plain English. Examples:

- "Q7 should be 0.5 on Numerical Accuracy, not 1 - the student wrote 4 instead of -4."
- "The scan quality on Q12 should be Acceptable, not Good - the working ran into the page margin."
- "Add a developmental nudge about the substitution method as an alternative to graphical reasoning."

Iterate until you're satisfied.

### Step 5 - Request the TEX bundle

Once the grading is locked, say:

```
Looks good. Generate the TEX bundle.
```

Claude will produce:
- The `<StudentName>_<AssignmentCode>_<Date>_Report.tex` file (full text shown in chat as a code artifact)
- A compiled PDF (if compilation tools are available in the environment)
- A note confirming the `ts_evalreport.sty` and `logo.png` files needed are the same ones already in the project.

### Step 6 - Compile locally

On your machine:

```bash
mkdir KiranVinuNiar_DOM2_2026-05-09
cd KiranVinuNiar_DOM2_2026-05-09
# Copy the four files into this folder:
#   - The .tex Claude generated
#   - ts_evalreport.sty (from the project templates)
#   - logo.png (from the project templates)
xelatex KiranVinuNiar_DOM2_2026-05-09_Report.tex
xelatex KiranVinuNiar_DOM2_2026-05-09_Report.tex   # second pass for cross-references
```

**Required:** `xelatex` engine. TeX Live 2022+ has everything.

### Step 7 - Quality check before sending

Run through `QUALITY_CHECKLIST.md` before sending the PDF to the student. Mandatory items:

- [ ] Student name spelled correctly throughout
- [ ] Assignment code and tier correct
- [ ] All 25 (or N) questions present and graded
- [ ] Math expressions render correctly (no missing symbols, no broken subscripts)
- [ ] No em-dashes anywhere (only hyphens)
- [ ] Closing note speaks to the student personally
- [ ] AI disclaimer present at the end
- [ ] Filename follows convention: `<StudentName>_<AssignmentCode>_<YYYY-MM-DD>_Report.pdf`

## Edge cases and how to handle them

### Student uploaded the wrong assignment

If the scan contains answers to a different topic than the question paper, stop. Ask the student to re-submit. Do not evaluate.

### Question paper or scan is missing pages

Tell Claude: "The scan is missing pages X-Y" or "The question paper PDF only has Q1-Q15, the rest are missing." Claude will evaluate only what's available and add a note in the report's specific-note section.

### Illegible handwriting on a question

Claude marks the dimension as "cannot evaluate" and the question score as 0. Add a `\tsScanNote{Working not legible - request student resubmit this question.}` line. Do NOT guess.

### Borderline scoring

Claude flags any score where the choice changes the band. Two examples:

- Student is at 74.5% with one borderline call - if you upgrade that to 1, they cross 75% and promote to AA. Decide carefully.
- Student is at 44.5% with one borderline call - if you upgrade, they move from "Foundational Gaps" to "Developing." Same care.

When in doubt, score conservatively (lower) on Conceptual Understanding and Approach, generously on Numerical Accuracy and Presentation.

### Scan has identifying info from another student

Sometimes a scan accidentally includes another student's work in the corner. Ignore it. Do not include in the report. If it's a recurring issue, tell the batch coordinator.

### Student wrote insulting / inappropriate content

If a scan contains anything inappropriate (insults to teachers, slurs, etc.), do NOT quote it in the report. Note privately to Mohit. Continue evaluating only the mathematics.

## Naming conventions (locked)

- Output PDF / TEX filename: `<StudentName>_<AssignmentCode>_<YYYY-MM-DD>_Report.{pdf,tex}`
- StudentName: no spaces, CamelCase. "Kiran Vinu Niar" -> `KiranVinuNiar`. "B Sai Charan" -> `BSaiCharan`.
- AssignmentCode: as printed on the paper (DOM2, FUN3, INT1, etc.)
- Date: ISO format, the date you ran the evaluation
- Always use `_Report` suffix - this distinguishes evaluation reports from the assignment papers themselves

## When NOT to use this project

This project is for **subjective tier assignments** (WA, QA, AA). Do NOT use it for:

- ZA (Quizzes) - these are auto-graded by Google Forms; no Claude evaluation needed
- Mock JEE Main / Advanced - those use a separate result-card template
- Diagnostic tests - separate workflow
- Anything that's not a ThinkingSouls / EduBrahma assignment

## Getting help

If you're stuck:

1. Check `FRAMEWORK_REFERENCE.md` for rubric / tier / band definitions
2. Check `SAMPLE_PROMPTS.md` for prompt patterns
3. Check `QUALITY_CHECKLIST.md` for pre-send validation
4. If still stuck, message Mohit directly with the chat link

## Updating the framework

Do NOT change the rubric weights (40/20/20/10/10), the tier system, the band thresholds, or the LaTeX style file (`ts_evalreport.sty`) without explicit approval from Mohit. These are framework-level decisions and changing them silently breaks consistency across the student cohort.

If a rubric tweak is needed, propose it to Mohit, then update `FRAMEWORK_REFERENCE.md` and `0_PROJECT_INSTRUCTIONS.md` together so they stay in sync.
