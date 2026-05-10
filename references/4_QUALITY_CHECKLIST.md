# Quality Checklist - Before Sending the Report to the Student

Run through this list before delivering ANY evaluation report. Either you (Mohit) or the senior reviewer signs off.

## A. Identification (5 items)

- [ ] **Student name** matches the class roster spelling exactly. Check spaces, initials, diacritics.
- [ ] **Assignment code** matches what was issued (DOM2, FUN3, etc.)
- [ ] **Tier badge** in the header is correct (WA / QA / AA - never ZA)
- [ ] **Topic name** matches the question paper title
- [ ] **Evaluation date** is the date you ran the evaluation, not a default placeholder

## B. Scoring integrity (8 items)

- [ ] **All N questions present** in the report. Count them. If the assignment has 25 Qs, the report has 25 Q-cards.
- [ ] **Each question has all 5 dimension sub-scores** (CU, AM, SS, NA, PR) - none missing
- [ ] **Each question has a per-question total** that matches the formula: 0.40*CU + 0.20*AM + 0.20*SS + 0.10*NA + 0.10*PR
- [ ] **Aggregate percentage** matches sum of Q-scores / N * 100
- [ ] **Band assignment** matches the percentage:
  - >= 75% -> Trailblazer
  - 60-74% -> Qualifier
  - 45-59% -> Developing
  - < 45% -> Foundational Gaps
- [ ] **Promotion bar** matches the band-to-promotion logic from `FRAMEWORK_REFERENCE.md`
- [ ] **Rubric breakdown table** percentages add up consistently (per-dim avg = sum of Q sub-scores / N * 100 for each dimension)
- [ ] **Snowflake chart** visually matches the table values (no chart-vs-table mismatch)

## C. Per-question feedback (5 items)

- [ ] **Every question has a feedback paragraph** - none empty
- [ ] **Feedback is specific** - cites the student's actual working, not generic praise
- [ ] **Wrong answers are explained** - error named, correct approach shown, no shaming
- [ ] **Borderline scores have justification** in the feedback (not silent)
- [ ] **Scan notes** appear only on questions where scan quality is Acceptable or Poor

## D. Coaching analysis sections (NEW STRUCTURE - replaces old Pattern Diagnosis) (8 items)

### D.1 Misconceptions (conditional)
- [ ] **If 2+ questions show same conceptual error pattern, Misconceptions section IS present**
- [ ] **If only one-off slips exist, Misconceptions section is OMITTED entirely** (no empty container)
- [ ] **Each misconception has all 4 fields:** title, evidence (Q-numbers), what's happening, correct mental model

### D.2 SWOT Matrix (always)
- [ ] **All 4 quadrants present:** Strengths (green), Weaknesses (red), Opportunities (blue), Threats (amber)
- [ ] **3-5 bullets per quadrant** - no quadrant empty (even for 100% scorers, populate Weaknesses/Threats with next-tier items)
- [ ] **Each bullet has bold short title + 1-2 sentence elaboration**
- [ ] **Strengths bullets anchor to Q-numbers** as evidence

### D.3 Areas of Improvement (always)
- [ ] **Exactly 3 priorities** - Priority 1 (Critical, red), Priority 2 (Important, amber), Priority 3 (Nice to have, blue)
- [ ] **Each priority has all 4 fields:** title, Action, Measure, By when

### D.4 Concept Dependency Map (always)
- [ ] **Heat-map present** between Rubric Breakdown and SWOT Matrix (NOT between Areas of Improvement and Per-Question Evaluation - that's the old position)
- [ ] **5-8 concept rows** identified for the assignment topic
- [ ] **N question columns** (matches total question count)
- [ ] **Cell colors match question scores** (green = full, amber = partial, red = failed, grey = untested)

### D.5 Question fade gradient (always-on visual)
- [ ] **Question text fades to white** on the right portion of each `\tsQFunc` (visual check on a few questions)
- [ ] **YOUR ANSWER and EXPECTED remain fully readable** (fade scope correct)

### D.6 Summary Box (always)
- [ ] **Summary Box present** between Promotion bar and Rubric Breakdown on page 1
- [ ] **Label reads "S U M M A R Y" only** - NEVER "Parent Summary" or any other prefix
- [ ] **Plain-language content** - no rubric jargon, accessible to a parent or non-expert reader
- [ ] **Key facts bolded** (score, tier, next assignment)

### D.7 Tracking ID + QR Code (always)
- [ ] **Tracking ID present** on closing page after disclaimer/signature
- [ ] **Tracking ID format correct:** `TS-{tier}-{assignment}-{YYYYMMDD}-{studentInitials}-{seqNum}`
- [ ] **QR code renders** sharply and is scannable
- [ ] **QR encodes URL** `https://thinkingsouls.com/track/{TrackingID}` (placeholder for future dashboard)

## E. Closing note (3 items)

- [ ] **Addresses student by first name** (once, near the start)
- [ ] **Honest assessment** of what the score signals - no sugar-coating
- [ ] **Forward-looking** - names the next assignment, adjacent topic to start, speed target

## F. Scanning tips and disclaimer (3 items)

- [ ] **Scanning Tips section present** with all 10 tips in 5x2 grid
- [ ] **Specific-to-student scan note** added if any question scored Acceptable or Poor
- [ ] **AI disclaimer present** at the end (provided by `\tsDisclaimer` macro)

## G. Formatting and notation (8 items)

- [ ] **No em-dashes (—)** anywhere - only hyphens (-). Search the TEX file for `—` to confirm.
- [ ] **Standard sets use `\mathbb{}`** - search for bare `\R`, `\N`, `\Z`, `\Q`, `\C` outside math mode and ensure no plain "R" appears as the reals
- [ ] **Inverse trig uses `\sin^{-1}`** style (or `\operatorname{arcsec}` for arcsec/arccsc/arccot)
- [ ] **All math compiles** without errors (check `xelatex` log)
- [ ] **No "Overfull \hbox"** warnings on actual content (warnings on labels are OK)
- [ ] **Page count is reasonable** - typically 12-14 pages for a 25-Q WA evaluation. Way more or less = something is broken.
- [ ] **Headings are flush-left** (no first-line indent on H1/H2/H3/H4)
- [ ] **Per-question card not split across pages** - each card sits fully on one page

## H. Visual quality (6 items)

- [ ] **Header band shows logo + brand name + tier badge** on every page (not just page 1)
- [ ] **Logo has transparent background** - the sun-burst graphic should sit on the white header band, NOT a black/grey rectangle. If you see a colored box behind the logo, the PNG is not RGBA - replace with `templates/logo.png`.
- [ ] **Footer shows page number, student/tier/code, and ThinkingSouls URL** on every page
- [ ] **Snowflake chart renders** as smooth blob (not sharp pentagon)
- [ ] **Dimension tiles align across rows** - all 100% values at same baseline, all "Weighted Score" lines at same baseline
- [ ] **Color coding consistent** - green (>=100%), amber (50-99%), red (<50%) on dim tiles; matching color on band badge

## I. Filename and delivery (3 items)

- [ ] **Filename follows convention:** `<StudentName>_<AssignmentCode>_<YYYY-MM-DD>_Report.pdf`
- [ ] **CamelCase StudentName** with no spaces, no diacritics, no periods
- [ ] **PDF preview opens correctly** - last sanity check by opening the PDF in your viewer

## J. Privacy and safety (3 items)

- [ ] **No content from other students** visible in the scan was included or referenced
- [ ] **No personal info** (parents' names, phone numbers, addresses) leaked into the report
- [ ] **No inappropriate content** from the student's submission carried into the report

## K. Junior-evaluator-specific (only if a junior produced the draft)

- [ ] **Reviewed by Mohit** before sending
- [ ] **One-line "Draft prepared by junior, reviewed by Mohit Sardana"** note included
- [ ] **Senior signature** added in the closing block

---

## Sign-off line

```
Reviewed and approved for delivery to student.
Reviewer: ______________
Date: ______________
```

---

## What to do if a checklist item fails

- **A or B (identification / scoring integrity) fails** - DO NOT SEND. Re-evaluate.
- **C, D, E (feedback / patterns / closing) fails** - return to Claude with specific revision request, regenerate.
- **F (tips / disclaimer) fails** - regenerate the TEX with the missing block.
- **G (formatting) fails** - search and replace in the TEX, recompile.
- **H (visual) fails** - check `ts_evalreport.sty` was loaded; recompile with xelatex (twice).
- **I (filename) fails** - rename, no need to recompile.
- **J (privacy) fails** - DO NOT SEND. Escalate to Mohit immediately.
- **K (junior review) fails** - get Mohit's review before sending.

## Quick visual sanity test (30 seconds)

If you only have 30 seconds, do this:

1. Open page 1 - is the snowflake chart there? Does the table next to it match? Does the band badge color match what you'd expect for the percentage?
2. Open page 5 (or wherever the cards begin) - do all 5 dimension tiles render as colored blocks with percentages and "Weighted Score = X.XX"?
3. Open the last page - is the AI disclaimer there?

If yes to all three, you're 90% safe. The other 10% is the spelling, scoring math, and feedback specificity - that's why the full checklist exists.
