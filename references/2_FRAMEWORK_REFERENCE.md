# Framework Reference - ThinkingSouls Evaluation System

This document captures the locked-in decisions for evaluating subjective assignments. Treat these as fixed unless Mohit Sardana explicitly approves a change.

## 1. The Standard Subjective Rubric

Every question in WA, QA, and AA tiers is evaluated on five dimensions. Each dimension is scored on a 3-point scale:

| Score | Meaning |
|---|---|
| 1.0 | Full mark on this dimension |
| 0.5 | Partially correct - some elements right, some wrong or missing |
| 0.0 | Not done, or fundamentally incorrect |

### The five dimensions

| Code | Name | Weight | Definition |
|---|---|---|---|
| CU | Conceptual Understanding | 40% | Does the student understand the underlying concept? Can they explain why the method works, not just apply it mechanically? |
| AM | Approach and Method | 20% | Did they pick the right strategy? Is the chosen method efficient and appropriate? |
| SS | Step-by-Step Execution | 20% | Are the intermediate steps logically connected, complete, and shown in order? |
| NA | Numerical Accuracy | 10% | Are the calculations free of arithmetic / algebraic errors? |
| PR | Presentation and Clarity | 10% | Is the answer readable, well-organised, with the final answer clearly marked? |

### Per-question score formula (LOCKED)

```
Q = 0.40*CU + 0.20*AM + 0.20*SS + 0.10*NA + 0.10*PR
```

Maximum per question: 1.00 mark. Aggregate across all N questions; total marks = N; percentage = (sum of all Q-scores / N) * 100.

### Scoring discipline

- **Two students with the same wrong answer should get different scores** if their working shows different levels of understanding. The rubric is about the WORK, not just the final answer.
- **Conservative on CU and AM, generous on NA and PR** when borderline. CU is the most important dimension.
- **Never give 1.0 on a dimension if the student didn't actually demonstrate it.** Showing the formula but not using it correctly = 0.5 on AM, not 1.0.
- **If the working is fully correct but the final answer was copied wrong (e.g. lost a sign), give 0.5 on NA, full marks on the other four dimensions.**

## 2. Tier system

Four tiers, in order. Students progress one at a time.

| Code | Tier name | Type | Difficulty target | Promotion criterion |
|---|---|---|---|---|
| WA | Warm-Up Assignment | Subjective | Concept revision + JEE Main basics | >= 60% promotes to QA |
| ZA | Quiz | Objective (Google Form) | Concept check, MCQ | Auto-graded; not evaluated by Claude |
| QA | Qualifier's Assignment | Subjective | JEE Main hard + JEE Advanced easy | >= 75% promotes to AA |
| AA | Achiever's Assignment | Subjective | JEE Advanced level | >= 75% confirms mastery |

### No leapfrogging

A student who scores 95% on WA does NOT skip QA. They go to QA next.

A student who scores 50% on WA stays at WA - they revise and re-take WA (a different version, same topic).

### Why ZA is excluded

ZA quizzes are Google Forms with auto-graded MCQs. Results are computed instantly. Claude does not evaluate ZA submissions. If a user uploads a ZA, redirect them to the Google Form analytics dashboard.

## 3. Performance bands

| Band | Range | Color (in report) | Action |
|---|---|---|---|
| Trailblazer | >= 75% | tsGreen (#2E8540) | Promote to next tier |
| Qualifier | 60-74% | tsBlue (#0066CC) | (WA tier) Promote to QA; (QA/AA) revise and consolidate |
| Developing | 45-59% | tsAmber (#D97706) | Repeat current tier after targeted revision |
| Foundational Gaps | < 45% | tsRed (#C8102E) | Significant revision needed before retry |

> Note on naming: the ≥75% band is called **Trailblazer** (motivational, forward-looking - emphasises leading the path). The AA tier remains **Achiever's Assignment** (the original acronym source). The two names are deliberately distinct - "Trailblazer" describes a student's performance band; "Achiever's Assignment" describes a tier of difficulty.

### Band-to-promotion logic by tier

| Tier | Band | What happens |
|---|---|---|
| WA | Trailblazer (>=75%) | Promote to QA. Strong start - no remediation. |
| WA | Qualifier (60-74%) | Promote to QA. Note one or two gap areas in closing. |
| WA | Developing (45-59%) | Re-take WA after revision. Mentor session recommended. |
| WA | Foundational Gaps (<45%) | Pause assignment workflow. Conduct concept refresh first. |
| QA | Trailblazer (>=75%) | Promote to AA. |
| QA | Qualifier (60-74%) | Repeat QA after focused revision (next month). |
| QA | Developing | Drop back to WA on the topic, then re-attempt QA. |
| QA | Foundational Gaps | Drop back to WA, mentor session mandatory. |
| AA | Trailblazer (>=75%) | Mastery confirmed. Move to next topic / advanced problems. |
| AA | Qualifier | Solid - revisit weak dimensions, retry AA in 2 weeks. |
| AA | Developing | Drop back to QA on topic. |
| AA | Foundational Gaps | Drop back to WA. |

## 4. Scan quality assessment (per question)

Every question gets a scan-quality grade.

| Grade | When to assign | Color in report |
|---|---|---|
| Excellent | Perfect scan: even lighting, no thumb in frame, page flat, sharp focus, all working clearly visible | tsGreen |
| Good | Readable, evaluation not affected, minor issues (slight glare, edge slightly clipped but content visible) | tsBlue |
| Acceptable | Visible issue (skewed page, thumb in frame, fold crease cuts through working, sketch partly clipped) but content still readable enough to evaluate | tsAmber |
| Poor | Parts illegible or missing - evaluation degraded. Score reflects only what could be read. | tsRed |

If any question scores "Poor", add a `\tsScanNote{...}` line on that question's card with one specific sentence describing the issue.

If 3 or more questions score "Poor" or worse, the entire submission should be returned for re-scan rather than evaluated.

## 5. Coaching analysis sections (replaces old "Pattern Diagnosis")

Every report includes the following analytical sections AFTER the Rubric Breakdown and BEFORE the Per-Question Evaluation. These replace the old "Pattern Diagnosis" (Strengths + Developmental Nudges) with a richer coaching structure.

### 5.1 Misconceptions Identified (CONDITIONAL - omit if none)

A misconception is a *systematic* wrong mental model demonstrated across 2+ questions. NOT a one-off calculation slip.

**Show this section ONLY when** 2+ questions reveal the same conceptual error pattern.

**Skip the section entirely** if the student has only one-off slips, no patterns. (For 100% scorers, this section is always omitted.)

For each misconception, provide:
- **Title** - short label of the wrong model (e.g. "Absolute value treated as always positive")
- **Evidence** - the question numbers where it appeared (e.g. "Q3, Q11, Q15")
- **What's happening** - what the student is actually doing (their wrong reasoning)
- **Correct mental model** - the right way to think about it

LaTeX macro: `tsMisconceptions` environment with `\tsMisconception{title}{evidence}{whats-happening}{correct-model}` items.

### 5.2 SWOT Matrix (ALWAYS shown)

A 2x2 grid that gives the student a strategic picture at the current tier.

| Quadrant | Color | Definition |
|---|---|---|
| **Strengths** | Green | Habits and skills currently demonstrated. Anchored to evidence (Q-numbers). |
| **Weaknesses** | Red | Current gaps in execution or understanding. Specific. |
| **Opportunities** | Blue | What the next tier opens up if these strengths are leveraged. Forward-looking. |
| **Threats** | Amber | Risks if weaknesses aren't addressed before the next tier. Specific consequences. |

3-5 bullets per quadrant. Each bullet: bold short title + 1-2 sentence elaboration.

**Even for a 100% scorer**, populate Weaknesses and Threats with next-tier-relevant items (e.g., "method-selection efficiency", "JEE Advanced has different bracket-discipline stakes"). The SWOT is forward-looking, not just a backward grade.

LaTeX macro: `\tsSWOT{S-bullets}{W-bullets}{O-bullets}{T-bullets}` with `\tsSWOTpoint{title}{body}` inside each.

### 5.3 Areas of Improvement (ALWAYS shown - priority-ranked)

3 actionable improvements, ranked by priority. Visual design uses an **editorial / magazine-cover aesthetic**: oversized priority numerals (01/02/03) in color-flooded blocks on the left, with title and tracked-uppercase labels (ACTION / MEASURE / BY WHEN) on the right.

| Priority | Label | Color | Use for |
|---|---|---|---|
| 1 | Critical | Red | Must fix before next tier; causes major mark loss otherwise. |
| 2 | Important | Amber | Significant improvement; worth focused work in the next 1-2 weeks. |
| 3 | Nice to have | Blue | Quality-of-life improvement; build the habit gradually. |

For each improvement, provide:
- **Title** - concrete action label
- **Action** - what specifically to do (a drill, a habit, a re-do)
- **Measure** - how to know it's working (success criterion)
- **By when** - target deadline relative to next tier attempt

LaTeX macro: `tsImprovements` environment with `\tsImprove{rank}{labelText}{labelColor}{title}{action}{measure}{by-when}` items.

### Replacement of old sections

The old "Pattern Diagnosis" section (with `\tsHone{Pattern Diagnosis}` + Strengths bullets + Developmental nudges bullets) is **deprecated**. Do not generate it for new reports. The new structure replaces it entirely.

If you find a legacy template still using `Pattern Diagnosis`, replace it with: optional Misconceptions section, then SWOT Matrix, then Areas of Improvement.

### 5.4 Concept Dependency Map (ALWAYS shown)

A heat-map visualization placed AFTER Rubric Breakdown and BEFORE the SWOT Matrix. Pedagogical sequence: dimension breakdown -> concept landscape -> strategic picture -> action plan -> evidence.

**Purpose:** Shows which underlying concepts each question tests, colored by per-question performance. Lets the student see at a glance which concepts cluster across the assignment and where their performance pattern lies.

**Structure:**
- Rows = concepts (5-8 typical for a topic)
- Columns = questions (Q1 to QN)
- Cells colored by score: green (full), amber (partial), red (failed), grey (untested by that question)

**Concept selection guidance:** identify 5-8 distinct underlying mathematical concepts the assignment tests. For Domain of Functions, typical concepts include: constraint extraction, square root non-negativity, log argument positivity, absolute value handling, denominator non-zero, inverse trig domain, GIF/fractional part, composition of nested layers.

LaTeX macros:
- `\begin{tsConceptMap}{N}` ... `\end{tsConceptMap}` (N = number of questions)
- `\tsConceptMapHeader{1 &2 &3 ... &N}` (explicit Q-number header row)
- `\tsConceptRow{Concept name}{\tsCG &\tsCN &\tsCG &...}` (one row per concept)
- Cell shortcuts: `\tsCG` (green/full), `\tsCA` (amber/partial), `\tsCR` (red/failed), `\tsCN` (grey/untested)

### 5.5 Question fade gradient (ALWAYS active)

Every question's function display (`\tsQFunc`) automatically applies a fade-to-white gradient over its right portion. This is a **privacy and tease aesthetic** - a viewer over the student's shoulder sees the question opening and function class but not the full problem.

**Behavior:** the fade is implemented in `\tsQFunc` rendering inside `tsQCard`. No additional macro calls needed - just write `\tsQFunc{...}` as usual and the fade is applied automatically.

**Scope:** fade applies to the question text only. The "YOUR ANSWER" / "EXPECTED" comparison stays fully visible (pedagogical core). The dimension tiles, feedback, and scan notes are unaffected.

**To temporarily disable** (e.g., for an internal QA report where you need full readability), the STY would need a flag toggle - currently always-on. Raise this with Mohit if needed.

### 5.6 Summary Box (ALWAYS shown)

A 4-5 line plain-language summary placed at the top of page 1, just below the Promotion bar and above the Rubric Breakdown. Anyone (parent, student, mentor, school admin) can read it without understanding the rubric.

**Important naming:** the section is labelled simply "S U M M A R Y" - **never "Parent Summary"** even though parents are a primary audience. The label stays neutral so any reader can engage with it.

**Content guidance:**
- Lead with the headline fact (score + tier promotion outcome)
- Name 2-3 key strengths in plain language (no rubric jargon)
- Name 2-3 focus areas for the next stage
- End with a concrete next step (next assignment, target date)
- Bold the most important factual elements (score, tier, next assignment)

LaTeX macro: `\tsSummaryBox{body text with \textbf{...} highlights}`. Blue accent strip on the left, light grey background, tracked uppercase "S U M M A R Y" header.

### 5.7 Tracking ID (ALWAYS shown)

Every report carries a unique tracking identifier, placed on the closing page after the disclaimer and signature.

**Tracking ID format:** `TS-{tier}-{assignment}-{YYYYMMDD}-{studentInitials}-{sequenceNum}`

Example: `TS-WA-DOM2-20260509-KVN-001`

Components:
- `TS` - ThinkingSouls prefix (fixed)
- `{tier}` - WA / QA / AA
- `{assignment}` - assignment code (DOM2, FUN3, etc.)
- `{YYYYMMDD}` - evaluation date (no separators)
- `{studentInitials}` - student initials (e.g. KVN for Kiran Vinu Niar)
- `{sequenceNum}` - 3-digit zero-padded sequence (001 for first, 002 for re-evaluation, etc.)

**Purpose:** parent/student can quote the tracking ID when contacting ThinkingSouls about a specific evaluation. The ID identifies the exact submission, evaluation date, and rubric version used.

**No QR code.** A QR code was considered but removed - currently no consumer-facing dashboard exists at a target URL, so the QR would have no functional benefit. The plain-text tracking ID is sufficient for support and audit needs. If a dashboard is built in the future, the tracking block can be re-extended to include a QR code.

LaTeX macro: `\tsTrackingBlock{TrackingID}` (single argument). Renders as a light grey card with tracked-uppercase "T R A C K I N G  I D" label, the ID in monospace, and a brief italic instruction below.

## 6. Tone and voice

### Question feedback (per-question card)

- Length: 2 to 4 sentences. Specific.
- Voice: crisp coach. "You did X correctly. Here's where it could be sharper: Y." Not "Good job!" generic praise.
- For wrong answers: name the error, show the right approach, do NOT shame.
- For correct answers with weak working: praise the answer, then note what would make the working stronger.
- Always cite specifics: "in step 3, when you wrote 2x = ...", "your final answer of (-2, 3]", etc.

### Misconceptions section (when shown)

- Each misconception: short bold title, then "What's happening" (1-2 sentences) + "Correct mental model" (1-2 sentences).
- Tone: diagnostic, not accusatory. "The student is treating X as Y" not "The student doesn't know X."
- Always end with the constructive correction, not the error.

### SWOT Matrix bullets

- 3 to 5 bullets per quadrant.
- **Strengths**: anchor to evidence with question numbers. "Disciplined constraint extraction" + "Q1 to Q25, intersections written explicitly."
- **Weaknesses**: specific and named, not generic. "Method-selection efficiency on Q21" beats "could be more efficient."
- **Opportunities**: forward-looking. "Ready for graphical reasoning at scale at QA level" - what becomes possible.
- **Threats**: name the consequence. "JEE Advanced has different bracket-discipline stakes - a single wrong bracket can flip a 4-mark question to 0."

### Areas of Improvement bullets

- Exactly 3 priorities (Critical, Important, Nice to have).
- Each has Action / Measure / By when.
- Action: a concrete drill, habit, or re-do. Not vague advice.
- Measure: a success criterion that's externally checkable.
- By when: tied to the next tier attempt or a habit-building horizon.

### Closing note

- Personal: address the student by first name once at the start.
- Honest: name what the score signals, not what it doesn't.
- Forward-looking: where to go next - next assignment, adjacent topic, speed target.
- Length: ~150-250 words. Not a thesis.

## 7. Naming and notation conventions (LOCKED)

- **Em-dash (—) is forbidden.** Use hyphen (-) everywhere - in feedback, closing notes, titles, all generated text.
- **Standard sets in math mode:** `\mathbb{R}`, `\mathbb{N}`, `\mathbb{Z}`, `\mathbb{Q}`, `\mathbb{C}`. Never bare `R`, `N`, etc.
- **Inverse trig:** `\sin^{-1}`, `\cos^{-1}`, `\tan^{-1}` - prefer this over `\arcsin`, `\arccos`, `\arctan`. For arcsec, arccsc, arccot use `\operatorname{arcsec}` etc.
- **Interval vs union form:** at JEE Advanced level, prefer union of intervals: `(0, 1) cup (1, 2) cup (2, 3) cup (3, 4)` over set-builder `(0, 4) - {1, 2, 3}`. Note both as "equivalent forms" if appropriate.
- **Endpoint reasoning:** when writing intervals with mixed open/closed brackets, explain why each endpoint is open or closed (denominator zero, domain restriction, etc.).
- **Salutation:** in any direct address (email, parent communication), default to "Mr./Ms. [Last Name]". For coaching segment outreach, "Sir" is an optional warmer variant.

## 8. Output filename convention (LOCKED)

`<StudentName>_<AssignmentCode>_<YYYY-MM-DD>_Report.{pdf,tex}`

Examples:
- `KiranVinuNiar_DOM2_2026-05-09_Report.pdf`
- `BSaiCharan_FUN3_2026-05-12_Report.tex`
- `RheaSharma_INT1_2026-06-01_Report.pdf`

**StudentName** rules:
- No spaces, CamelCase
- Use full name as on roll list, including initials
- "Kiran Vinu Niar" -> `KiranVinuNiar`
- "B Sai Charan" -> `BSaiCharan` (initial included, no period)
- Diacritics: drop them. "Pradnya Mukherjeé" -> `PradnyaMukherjee`

## 9. The LaTeX style file (locked at v1.x)

`ts_evalreport.sty` provides all macros for the report. It is the single source of visual truth. **Do not edit it during routine evaluations.** Changes go through Mohit.

Key macros (full reference in `templates/README_TEMPLATE.md`):

- Headings: `\tsHone`, `\tsHtwo`, `\tsHthree`, `\tsHfour`
- Page-1 blocks: `\tsStudentBlock`, `\tsScoreBlock`, `\tsPromotionBar`, `\tsSummaryBox`
- Rubric breakdown: `\begin{tsRubricSplit}{cu}{am}{ss}{na}{pr} ... \end{tsRubricSplit}` (snowflake + table side by side)
- **Concept dependency map:** `\begin{tsConceptMap}{N}` ... `\tsConceptMapHeader{...}` + `\tsConceptRow{...}{...}` ... `\end{tsConceptMap}` (cells: `\tsCG/\tsCA/\tsCR/\tsCN`)
- **Coaching sections:**
  - `\begin{tsMisconceptions}` ... `\tsMisconception{title}{evidence}{whats-happening}{correct-model}` ... `\end{tsMisconceptions}`
  - `\tsSWOT{S-bullets}{W-bullets}{O-bullets}{T-bullets}` with `\tsSWOTpoint{title}{body}` inside
  - `\begin{tsImprovements}` ... `\tsImprove{rank}{labelText}{labelColor}{title}{action}{measure}{by-when}` ... `\end{tsImprovements}`
- Per-question card: `\begin{tsQCard}{n}{topic}{scanLabel}{scanColor}{score}{maxScore} ... \end{tsQCard}` (fade gradient applied automatically to `\tsQFunc`)
- Bullets (general): `\begin{tspoints} \item ... \end{tspoints}`
- Scan tips: `\begin{tsScanTips}` ... `\end{tsScanTips}`
- Disclaimer: `\tsDisclaimer`
- Signature: `\tsSignature`
- **Tracking ID:** `\tsTrackingBlock{TrackingID}` (single argument, no QR code)

## 10. Engine and packages

- Compile with: `xelatex` (twice for cross-references)
- Required packages: tcolorbox, tikz, fancyhdr, enumitem, colortbl, tabularx, array, graphicx, hyperref, ragged2e, microtype, needspace, fontspec, unicode-math
- Required fonts: TeX Gyre Heros (body), Latin Modern Math (math)
- All standard - no special downloads needed beyond TeX Live 2022+.
