# `ts_evalreport.sty` Macro Reference

This is the LaTeX style file that powers all ThinkingSouls evaluation reports. Read it whenever you're filling out `REPORT_TEMPLATE.tex`.

## Files in this folder

- `ts_evalreport.sty` - the style file (do NOT modify)
- `REPORT_TEMPLATE.tex` - blank skeleton with `[PLACEHOLDER]` values
- `logo.png` - ThinkingSouls red flower-burst logo (referenced by the STY in the header)

## Compilation

```bash
xelatex Report.tex
xelatex Report.tex   # second pass for cross-references
```

Engine: `xelatex` (uses `fontspec` and `unicode-math`).
Required packages: tcolorbox, tikz, fancyhdr, enumitem, colortbl, tabularx, array, graphicx, hyperref, ragged2e, microtype, needspace.
Required fonts: TeX Gyre Heros (body), Latin Modern Math (math). Both ship with TeX Live.

## Color tokens

| Name | Hex | When to use |
|---|---|---|
| `tsRed` | `#C8102E` | Primary brand color, headings, emphasis |
| `tsDarkRed` | `#9B0C24` | Darker red for accents |
| `tsText` | `#1A1A1A` | Body text |
| `tsGrey` | `#666666` | Secondary text, captions, footer |
| `tsLightGrey` | `#E5E5E5` | Hairlines, table borders |
| `tsBorder` | `#D4D4D4` | Card borders |
| `tsGreen` | `#2E8540` | Mastery / Excellent / Trailblazer band |
| `tsAmber` | `#D97706` | Acceptable / Developing / Scan note |
| `tsBlue` | `#0066CC` | Good / Qualifier band |
| `tsBgLight` | `#FAFAFA` | Card answer-row background |
| `tsBgGreen` | `#F0F8F4` | Promotion bar background |

## Macros - quick reference

### Header / footer setup (call once near the top of the document)

```latex
\tsSetHeader{breadcrumb text}{tier letters}
\tsSetTier{tier letters}{tier full name}
\tsSetFooter{left footer text}{right footer text}
```

### Page-1 hero blocks

```latex
\tsStudentBlock{Full Name}{Assignment Code - Description}{Topic}{DD MMM YYYY}

\tsScoreBlock{percent\%}{marks}{maxMarks}{band}{bandColor}{verdict}
% Example:
\tsScoreBlock{100.0\%}{25.00}{25}{Trailblazer}{tsGreen}{Qualifies for Qualifier's Assignment (QA)}

\tsPromotionBar{accentColor}{bgColor}{LABEL}{textColor}{verdictText}{noteText}
% Example:
\tsPromotionBar{tsGreen}{tsBgGreen}{PROMOTION:}{tsText}{Promoted to QA.}{Threshold cleared by 25 points.}

% Summary Box - plain-language summary for any reader
% Label is "S U M M A R Y" only (NEVER "Parent Summary")
\tsSummaryBox{Body text. Use \textbf{...} to highlight key facts.}
```

### Headings (use these, not raw `\section`)

```latex
\tsHone{Big section heading}            % 14pt red bold
\tsHtwo{Subsection}                     % 12pt red bold
\tsHthree{Paragraph head}               % 11pt black bold
\tsHfour{Minor heading}                 % 10pt red bold
```

### Rubric breakdown (page 1)

The standard layout is the snowflake + table side by side:

```latex
\begin{tsRubricSplit}{cuPct}{amPct}{ssPct}{naPct}{prPct}
    \rubricRowC{Conceptual Understanding}{40\%}{[CU]\%}{\color{tsGreen}\textbf{Mastery}}
    \rubricRowC{Approach \&\ Method}{20\%}{[AM]\%}{\color{tsGreen}\textbf{Mastery}}
    \rubricRowC{Step-by-Step Execution}{20\%}{[SS]\%}{\color{tsGreen}\textbf{Mastery}}
    \rubricRowC{Numerical Accuracy}{10\%}{[NA]\%}{\color{tsGreen}\textbf{Mastery}}
    \rubricRowC{Presentation \&\ Clarity}{10\%}{[PR]\%}{\color{tsGreen}\textbf{Mastery}}
\end{tsRubricSplit}
```

The first 5 args to `tsRubricSplit` are the dimension AGGREGATE percentages (used to draw the snowflake). The 5 `\rubricRowC` lines fill the table.

For full-width-only table (no snowflake), use `tsRubricTable` and `\rubricRow` instead.

### Hanging-indent bullets (general use)

```latex
\begin{tspoints}
    \item \textbf{Point title.} Body text here. Wrapped lines align under the body, not the bullet.
    \item \textbf{Another point.} ...
\end{tspoints}
```

### Coaching sections (Misconceptions / SWOT / Areas of Improvement)

These three sections replace the old "Pattern Diagnosis" structure. Sequence on the report:
1. Misconceptions (CONDITIONAL - only if 2+ questions show the same conceptual error pattern)
2. SWOT Matrix (ALWAYS)
3. Areas of Improvement (ALWAYS - exactly 3 priorities)

**Misconceptions** (conditional - omit entire section if no real misconceptions):

```latex
\tsHone{Misconceptions Identified}

\begin{tsMisconceptions}
    \tsMisconception%
        {Title of misconception}%
        {Q-numbers where seen, e.g. Q3, Q11, Q15}%
        {What's happening - the wrong mental model in action}%
        {The correct mental model}
    \tsMisconception%
        {...}%
        {...}%
        {...}%
        {...}
\end{tsMisconceptions}
```

**SWOT Matrix** (always shown):

```latex
\tsHone{SWOT Matrix}

\tsSWOT
    {% STRENGTHS bullets (green)
        \tsSWOTpoint{Strength 1 title.}{Body}
        \tsSWOTpoint{Strength 2 title.}{Body}
    }
    {% WEAKNESSES bullets (red)
        \tsSWOTpoint{Weakness 1 title.}{Body}
    }
    {% OPPORTUNITIES bullets (blue)
        \tsSWOTpoint{Opportunity 1 title.}{Body}
    }
    {% THREATS bullets (amber)
        \tsSWOTpoint{Threat 1 title.}{Body}
    }
```

The 4 boxes auto-arrange in a 2x2 grid: STRENGTHS top-left, WEAKNESSES top-right, OPPORTUNITIES bottom-left, THREATS bottom-right. Each box is fixed at 6.5cm height; bullets must fit (3-5 per quadrant typical).

**Areas of Improvement** (always shown - 3 priorities):

```latex
\tsHone{Areas of Improvement}

\begin{tsImprovements}
    \tsImprove{1}{Critical}{tsRed}%
        {Title of improvement}%
        {Action - what to do}%
        {Measure - success criterion}%
        {By when - timeline}
    \tsImprove{2}{Important}{tsAmber}%
        {...}%
        {...}%
        {...}%
        {...}
    \tsImprove{3}{Nice to have}{tsBlue}%
        {...}%
        {...}%
        {...}%
        {...}
\end{tsImprovements}
```

Priority badge colors:
- Priority 1 / Critical -> tsRed
- Priority 2 / Important -> tsAmber
- Priority 3 / Nice to have -> tsBlue

### Concept Dependency Map (heat-map)

Placed AFTER Rubric Breakdown and BEFORE the SWOT Matrix. Shows which concepts each question tests, colored by performance.

```latex
\tsHone{Concept Dependency Map}

\begin{tsConceptMap}{25}
    \tsConceptMapHeader{1 &2 &3 &4 &5 &6 &7 &8 &9 &10 &11 &12 &13 &14 &15 &16 &17 &18 &19 &20 &21 &22 &23 &24 &25}
    \tsConceptRow{Constraint extraction}{\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG &\tsCG}
    \tsConceptRow{Square root non-negativity}{\tsCG &\tsCN &\tsCG &\tsCG &\tsCN &...}
    % ... more concept rows
\end{tsConceptMap}
```

Cell shortcuts:
- `\tsCG` = green (full mark on this concept for that Q)
- `\tsCA` = amber (partial)
- `\tsCR` = red (failed)
- `\tsCN` = neutral grey (untested by that Q)

For each row, write out exactly N cells separated by `&` (matching the question count).

Concept selection guidance: identify 5-8 distinct mathematical concepts the assignment tests. For Domain of Functions: constraint extraction, square root non-negativity, log argument positivity, absolute value handling, denominator non-zero, inverse trig domain, GIF/fractional part, composition of nested layers.

### Question fade gradient (automatic)

Every question's function (`\tsQFunc{...}`) automatically gets a fade-to-white gradient on its right side. Privacy + tease: a shoulder-surfer sees the opening but not the full problem. No additional macro calls needed - the fade is built into how `\tsQFunc` renders inside `tsQCard`.

The fade scope is the question text only. Answer comparison ("YOUR ANSWER" vs "EXPECTED") stays fully visible.

### Per-question card

```latex
% Set state BEFORE the environment opens
\tsQFunc{$f(x) = ...$}                          % the question / function
\tsQAnswer{your answer}{expected answer}         % side-by-side comparison
\tsQDimRow{cu}{am}{ss}{na}{pr}                   % integer percentages 0-100
\tsQFeedback{Feedback prose ...}
\tsScanNote{Optional - omit for Excellent or Good scans}

% Now render the card
\begin{tsQCard}{qNum}{topic}{scanLabel}{scanColor}{score}{maxScore}
\end{tsQCard}
```

The 5 dimension tiles auto-color based on percentage:
- 100% -> green
- 50-99% -> amber
- < 50% -> red

Tiles are 3.2cm wide each (16cm total), centered within the card. Each tile shows: 2-line label (top), big percentage (middle), Weighted Score = X.XX (bottom). All five tiles align at the same baseline.

### Scan tips grid (closing pages)

```latex
\begin{tsScanTips}
    \tsTip{1}{Title.} Body...
    &
    \tsTip{2}{Title.} Body...
    \\\hline
    \tsTip{3}{Title.} Body...
    &
    \tsTip{4}{Title.} Body...
    \\\hline
    % ... 5 rows total, 10 tips
\end{tsScanTips}
```

### Closing blocks

```latex
\tsDisclaimer    % AI disclaimer in amber tcolorbox
\tsSignature     % "Evaluated by..." line + Mohit credit

% Tracking ID (placed on the closing page after disclaimer/signature)
% Format: TS-{tier}-{assignment}-{YYYYMMDD}-{studentInitials}-{seqNum}
% Single argument - no QR code (the dashboard URL doesn't exist yet)
\tsTrackingBlock{TS-WA-DOM2-20260509-KVN-001}
```

## Special notation rules (LaTeX)

- Standard sets: `\mathbb{R}`, `\mathbb{N}`, `\mathbb{Z}`, `\mathbb{Q}`, `\mathbb{C}`
- Inverse trig: `\sin^{-1}`, `\cos^{-1}`, `\tan^{-1}`
- arcsec/arccsc/arccot: use `\operatorname{arcsec}` etc.
- Greek: `\pi`, `\theta`, `\alpha`, etc. (loaded by unicode-math)
- Set difference: `\setminus` or `-`
- Union/intersection: `\cup`, `\cap`
- Forall/exists: `\forall`, `\exists`

## Page geometry (do not change)

- A4 (21 x 29.7 cm)
- Margins: 2 cm all around
- Content width: 17 cm
- Header band: 2.8 cm
- Footer: 1.2 cm

## Common pitfalls

- **Em-dash (—) is forbidden.** Use hyphen (-). The STY does not auto-convert.
- **\tsScanNote{...} is optional** - omit it entirely if the scan is Excellent or Good. Don't pass an empty argument.
- **\tsQDimRow expects integers 0-100**, not decimals 0-1. Pass `\tsQDimRow{100}{50}{75}{100}{100}` not `\tsQDimRow{1.0}{0.5}{0.75}{1.0}{1.0}`.
- **Per-question cards are NOT breakable** - if a card won't fit on the current page, it pushes to the next page automatically (via `\needspace{6.5cm}`). Don't add manual `\newpage`.
- **\tsRubricSplit has fixed dimensions** for snowflake (7cm) and table (10cm). Don't try to resize - if you need a different layout, ask Mohit to extend the STY.

## When something doesn't render

1. Check the `xelatex` log for explicit errors first
2. Verify `ts_evalreport.sty` is in the same folder as your `.tex` file (not in a parent dir)
3. Verify `logo.png` is in the same folder
4. Confirm engine is `xelatex`, not `pdflatex` (which lacks `fontspec`)
5. If a tile or card looks wrong, check the order of `\tsQFunc` / `\tsQAnswer` / `\tsQDimRow` / `\tsQFeedback` calls BEFORE the `\begin{tsQCard}` line - they must come first

## Versioning

Current STY version: v1.x (see `\ProvidesPackage` line in the file).

Changelog highlights:
- v1.0 - initial release
- v1.1 - 2cm margins, vertical-centering rubric table, H1/H2/H3/H4 hierarchy
- v1.2 - 3.2cm tiles, fixed-baseline alignment across tiles, "Weighted Score" naming, all 5 labels uniform 2-line
- v1.3 - smooth snowflake chart (Bezier), `tsRubricSplit` side-by-side layout

Do not edit the STY without coordination with Mohit. If you need a new macro or visual change, raise it with him before changing.
