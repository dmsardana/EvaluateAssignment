# Sample Prompts - EvaluateAssignment

Copy-paste prompts for common tasks. Edit the placeholders in [square brackets] with the actual values.

## Kickoff prompts

### A. Standard senior evaluation (Mohit / lead)

```
Evaluate this submission.

Student: [Full Name]
Batch: [SPARK-2027 / batch code]
Assignment: [DOM2 / assignment code]
Tier: [WA / QA / AA]
Topic: [Domain of Functions / topic name]
Date: [09 May 2026]

I am Mohit / senior evaluator. Proceed end-to-end and produce the TEX bundle in one shot.

Files attached: student submission, question paper [, answer key].
```

### B. Junior evaluator (with safeguards)

```
Evaluate this submission.

Student: [Full Name]
Batch: [SPARK-2027]
Assignment: [DOM2]
Tier: [WA / QA / AA]
Topic: [Domain of Functions]
Date: [09 May 2026]

I am a junior evaluator. Show me the per-question grading first and wait for my confirmation before generating the TEX bundle. Flag any borderline calls.

Files attached: student submission, question paper [, answer key].
```

### C. With explicit answer key

```
Evaluate this submission.

Student: [Full Name]
Batch: [SPARK-2027]
Assignment: [DOM2]
Tier: [WA]
Topic: [Domain of Functions]
Date: [09 May 2026]

I am Mohit. The third PDF is the official answer key - use it as the source of truth for correct answers. Flag any cases where the student's working leads to a different answer than the key, even if the student's reasoning is sound.

Files attached: student submission, question paper, answer key.
```

### D. Re-evaluation request (student / parent contested)

```
A parent has questioned the score on this previous evaluation. Please re-grade independently and explain any differences.

Student: [Full Name]
Original report date: [previous date]
Original total: [previous %]
Specific questions challenged: Q[#], Q[#]

Re-evaluate ONLY the challenged questions in detail. For each, show:
- Sub-scores you'd give now (CU/AM/SS/NA/PR)
- The original sub-scores (if visible in the prior report)
- A clear, neutral justification

Do not generate a new TEX bundle - just the re-evaluation analysis.

Files attached: student submission, question paper, prior evaluation report.
```

## Mid-evaluation correction prompts

### Override a specific question's score

```
Update Q[#]: change [dimension] from [old score] to [new score]. Reason: [brief justification].
```

Example:
```
Update Q7: change Numerical Accuracy from 1.0 to 0.5. Reason: student wrote x = 4 in the final union but the working clearly shows x in [3, 4], so the boundary is mishandled.
```

### Add or modify the scan note

```
On Q[#], add a scan note: "[exact text of note]"
```

### Coaching section adjustments (NEW)

**Add or remove a misconception:**
```
Add a misconception: "[title]" - seen in Q[#], Q[#]. What's happening: [...]. Correct model: [...]
```

```
Remove the misconception "[title]" - on review, this was a one-off slip on Q[#] only, not a pattern.
```

**Refine a SWOT bullet:**
```
In the SWOT Strengths quadrant, replace bullet 2 with: "[title]" - "[body]"
```

```
Move the bullet "[title]" from Weaknesses to Threats - the framing is more about future risk than current gap.
```

**Adjust priority of an Area of Improvement:**
```
Change "[improvement title]" from Priority 2 / Important to Priority 1 / Critical. Reason: this is a JEE Advanced-level discipline issue, not a quality-of-life one.
```

**Add or remove an Area of Improvement:**
```
Add a Priority 3 / Nice to have improvement: title "[...]", action "[...]", measure "[...]", by when "[...]".
```

```
Drop the Priority 3 area - keep only 2 priorities for this report. Student already has too much on their plate.
```

### Concept dependency map adjustments

**Modify a concept row:**
```
For the concept "Square root non-negativity", change Q[#] from green (full) to amber (partial) - on review, the student missed the boundary at x = 0.
```

**Add or remove a concept:**
```
Add a new concept row: "Endpoint inclusion/exclusion discipline" - tested in Q[#], Q[#], Q[#], all green.
```

```
Drop the "Composition / nested layers" concept row - it overlaps too much with "Constraint extraction" and isn't distinctive enough.
```

### Summary Box adjustments

**Tweak the summary content:**
```
Rewrite the Summary Box - the current version is too rubric-heavy. Make it more parent-friendly: lead with the score outcome, then 2 strengths, 2 focus areas, the next assignment. No mention of CU/AM/SS/NA/PR.
```

```
Tighten the Summary Box to 3 sentences max. The current version is too long.
```

```
Reminder: the Summary Box label is "S U M M A R Y" - never "Parent Summary" or any prefix.
```

### Tracking ID adjustments

**Generate a different sequence number:**
```
This is the second evaluation of this submission - use sequence number 002 in the tracking ID instead of 001.
```

**Custom URL for the QR code:**
```
For this report, the QR code should encode "mailto:admin@thinkingsouls.com?subject=Track-{ID}" instead of the default URL placeholder.
```

### Adjust the closing note tone

```
The closing note is too soft for this submission. The student got 52% with weak Step-by-Step Execution throughout. Rewrite the closing to be honest about the gap while staying constructive.
```

### Add a developmental nudge

```
Add a developmental nudge in Pattern Diagnosis: "[topic]. [What to work on]. [Why it matters at the next tier]."
```

## Output prompts

### Request the TEX bundle (end of evaluation)

```
Looks good. Generate the TEX bundle.
```

### Request only the PDF, no TEX

```
Skip the TEX file - I only need the compiled PDF.
```

### Request a one-page summary instead of full report

```
Skip the full report. Generate a one-page summary card with: total score, band, top 3 strengths, top 2 nudges, scan quality summary. Use the same branding.
```

(Note: this will need a new STY macro - flag to Mohit if requested.)

## Edge case prompts

### Scan has a missing page

```
The scan is missing pages [X-Y] (Q[#] to Q[#]). Evaluate only the questions visible. In the final report, add a Specific Note explaining the missing pages and asking the student to resubmit those questions for full evaluation.
```

### Working illegible on specific questions

```
The working on Q[#] and Q[#] is illegible. Mark these as "cannot evaluate" - score 0, scan quality Poor, and add a scan note for each. Adjust the percentage calculation to reflect only the questions that could be evaluated.
```

### Wrong assignment uploaded

```
This scan is for a different assignment than the question paper provided. The question paper is on [topic A] but the student's working appears to be on [topic B]. Stop the evaluation and produce a short message I can send the student asking them to re-submit the correct file.
```

### Student mixed up answers (Q3 working under Q5 heading, etc.)

```
The student's working is in non-sequential order - Q[#]'s solution appears to be on the page labeled Q[#]. Please match working to questions by content, not by page label. Note this in the Specific Note section without being judgmental.
```

## Multi-student batch prompts

### Evaluate a batch in sequence

```
I have 8 students in this batch (SPARK-2027) who attempted DOM2. I'll upload them one at a time. For each, give me the per-question grading and the TEX bundle. After all 8, also give me a batch summary: average %, distribution across bands, common patterns across the cohort.

Starting with Student 1: [Name]
```

### Batch summary at end

```
Now that all 8 are evaluated, produce a batch summary:
- Average percentage
- Distribution across bands (count per band)
- Top 3 common strengths across the batch
- Top 3 common gaps to address in the next class
- Names of students flagged for mentor session

Format as a markdown table I can paste into Slack.
```

## Reformatting prompts

### Switch to QA tier (if tier was wrong)

```
Re-do the evaluation as QA tier (not WA). Update:
- Tier badge in header
- Promotion threshold text (>=75% to AA, not >=60% to QA)
- Closing note framing (QA tier is not the start - speed and rigor expectations are higher)
```

### Add scan tips section (skipped earlier)

```
The closing pages are missing the Scanning Tips block. Please add the standard 10-point tips grid plus the specific note about [student-specific scan issues].
```

## Quality / sanity prompts

### Spot-check the math

```
Before generating the TEX bundle, double-check Q2, Q7, and Q21 - these are the questions where the student's reasoning is most non-standard. Show me your verification of each: what the student did, what the correct answer is, and whether they match.
```

### Verify endpoint discipline

```
For every question that involves intervals, verify the open/closed brackets match what the student wrote. Specifically check:
- Q8: should it be (-inf, -2) or (-inf, -2]?
- Q11: bracket at x = 0 - open or closed?
- Q21: closed at 0, open at 1?
```

### Check naming conventions

```
Before finalising, scan the entire generated text for em-dashes. Replace any with hyphens. Also confirm all standard sets use \mathbb{} not bare letters.
```

## Reference and meta prompts

### What does X mean?

```
What does the [Acceptable] scan quality mean exactly? When should I use it vs Good?
```

```
Walk me through how the per-question score formula gives 0.85 from sub-scores (1, 1, 0.5, 0, 1).
```

### Show me an example

```
Show me an example feedback paragraph for a question where the student got the right answer but the working has a logical gap.
```

```
Show me 3 examples of "developmental nudges" - one for a strong student, one for a borderline student, one for a weak student. Same topic, different tone.
```

### Help me with a specific situation

```
The student spelled their own name wrong in the submission header. The class roster says "Pradnya" but they wrote "Pragnya". Which spelling do I use?
```

(Default: use the roster spelling, not the submission spelling.)

## When NOT to use these prompts

These prompts assume you're inside the EvaluateAssignment Claude project with all reference files loaded. If you're starting a fresh chat outside the project, the rubric and conventions are not loaded - Claude will guess. Always evaluate inside the project.

If a prompt isn't covered here and you're unsure how to phrase it, just describe the situation in plain English. Claude will follow the project's custom instructions and respond in framework-aligned terms.
