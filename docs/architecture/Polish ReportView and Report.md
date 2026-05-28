# Report-views Polish — Plan

## Context

After the per-tier-report-views feature shipped (PRs #1, #2), the operator
flagged five readability fixes:

**Report (PDF):**
1. QRD table doesn't span full page width — ends ~5cm short of right margin.
2. Row heights too tight — header should be 10mm, body rows ≥ 6mm.
3. QRD missing a **Scan Quality** column (operator wants to see which questions
   were poorly scanned alongside their classification).

**UI (Settings → Report Components matrix):**
4. Category sub-header bands (Diagnostic / Structural / Coaching / Action / …)
   are barely visible (`bg-ink-5` on the near-black theme reads as "no band
   at all"). Each category should carry a distinct, **immediately scannable**
   visual treatment.
5. No row/column hover highlight — when clicking a checkbox in the middle of
   the matrix it's easy to lose track of which row + tier you're toggling.

A previous PR (`feat/qrd-full-width`, PR #3) attempted item #1 alone. It is
currently **open on GitHub, not merged**. This plan supersedes it: close PR #3
and bundle all five fixes into one new PR for one round of review.

### Skills applied
- `superpowers:using-superpowers` — process check; no brainstorming needed
  (concrete, well-scoped asks), already in `writing-plans` flow. Added one
  TDD-style helper test for the new field.
- `frontend-design:frontend-design` — applied to items 4-5. The matrix lives
  in a dark "terminal-ink" app; design direction is **editorial / disciplined**
  (not maximalist). Translation: category bands get **accent strips on the
  left + small caps label**, not just a tinted background; hover gives a
  **cross-hair** (row + column highlight) with the intersection cell tinted
  most heavily — the operator can always see "what am I about to toggle".
  No new fonts; we honor the existing palette (`tsGreen` / `tsAmber` etc.
  in LaTeX have UI analogues already), but use them with conviction.

---

## Files modified (one PR, `feat/report-views-polish`)

| File | What changes | Items |
|---|---|---|
| `tools/templates/report_template.tex` | Widen QRD to `\textwidth`; add SCAN column; header strut | 1, 2, 3 |
| `tools/templates/ts_evalreport.sty` | `\tsQrdRow` 6→8 args (+scan_quality, +color); add `\tsQrdHeaderStrut` (10mm) and `\tsQrdBodyStrut` (6mm) | 2, 3 |
| `tools/generate_report.py` | `make_qrd_rows` includes `scan_quality` per row | 3 |
| `tests/test_render_helpers.py` | New test pinning `scan_quality` field + default | 3 |
| `web/app/app/settings/report-views/matrix.tsx` | Category color map; **left accent strip + small-caps band**; hover state lifted to `Matrix`; row + col + intersection cross-hair tint; tier-header tint when its column is hovered; checkbox scale-up on hover | 4, 5 |

No catalogue, API, or DB changes — purely render/UI polish.

---

## Implementation steps

### Step 1 — Renderer: include `scan_quality` in QRD rows

In `tools/generate_report.py`, update `make_qrd_rows` (find by name) to add to
each appended dict:

```python
"scan_quality": q.get("scan_quality", "Good"),
```

`scan_color()` (already defined at `tools/generate_report.py:111`) maps
"Excellent" / "Good" / "Acceptable" / "Poor" → `tsGreen` / `tsBlue` /
`tsAmber` / `tsRed`. It's already registered as a Jinja global via
`build_jinja_env`, so the template can call it directly on the row's
`scan_quality`. No new helper needed.

### Step 2 — Test: pin the new field

Append to `tests/test_render_helpers.py`:

```python
def test_qrd_rows_includes_scan_quality_with_legacy_default():
    ev = {"questions": [
        {"number": 1, "scan_quality": "Poor"},
        {"number": 2},  # legacy (no scan_quality) -> "Good"
    ]}
    rows = make_qrd_rows(ev)
    assert rows[0]["scan_quality"] == "Poor"
    assert rows[1]["scan_quality"] == "Good"
```

Run: `python3 -m pytest tests/test_render_helpers.py -v` → 6 passed.

### Step 3 — Sty macros: row-height struts + 8-arg QRD row

In `tools/templates/ts_evalreport.sty`, replace the existing `\tsQrdRow` macro
block at the file end with:

```latex
% Vertical struts that force minimum row heights.
% Header row: 10mm tall. Body rows: 6mm minimum.
\newcommand{\tsQrdHeaderStrut}{\rule[-3mm]{0pt}{10mm}}
\newcommand{\tsQrdBodyStrut}{\rule[-2mm]{0pt}{6mm}}

% \tsQrdRow{number}{topic}{concept}{attempted}{difficulty}{lo}{scan_quality}{scan_color}
% 7 visible cells; the strut keeps the row at least 6mm tall regardless of
% content length. Scan quality is colored via the supplied tsGreen/tsBlue/
% tsAmber/tsRed color name.
\renewcommand{\tsQrdRow}[8]{%
  \tsQrdBodyStrut\textbf{#1} & #2 & #3 & #4 & #5 & #6 & {\color{#8}\textbf{#7}} \\%
}
```

`\renewcommand` because Task 8 already defined a 6-arg `\tsQrdRow`; we're
extending it.

### Step 4 — Template: widen QRD + SCAN column + header strut

In `tools/templates/report_template.tex`, replace the `qrd_table` block (find
by `((* if "qrd_table" in components *))`) with:

```jinja
((* if "qrd_table" in components *))
\needspace{6cm}
\par\vspace{0.5cm}
\tsHone{Question Response Data}

\par {\fontsize{9pt}{12pt}\selectfont\color{tsGrey}\textit{Per-question
classification: topic, concept, whether attempted, difficulty band,
learning objective, and scan quality.}}

\par\vspace{0.25cm}
\noindent
\begingroup
\setlength{\tabcolsep}{5pt}%
\renewcommand{\arraystretch}{1.0}%  % struts in the macro handle height now
\arrayrulecolor{tsLightGrey}%
\fontsize{8.5pt}{10pt}\selectfont
% Full-width QRD. Fixed widths: 0.8 + 3.8 + 1.6 + 0.7 + 0.7 + 1.5 = 9.1cm
% + 6 tabcolsep gaps x 10pt ~= 2.1cm
% => Concept column = \textwidth - 11.2cm (~5.8cm at the current 17cm width)
\begin{longtable}{@{}p{0.8cm}p{3.8cm}p{\dimexpr\textwidth-11.2cm\relax}p{1.6cm}p{0.7cm}p{0.7cm}p{1.5cm}@{}}
\hline
\tsQrdHeaderStrut
{\color{tsGrey}\fontsize{7.5pt}{9pt}\selectfont Q\#} &
{\color{tsGrey}\fontsize{7.5pt}{9pt}\selectfont TOPIC} &
{\color{tsGrey}\fontsize{7.5pt}{9pt}\selectfont CONCEPT} &
{\color{tsGrey}\fontsize{7.5pt}{9pt}\selectfont ATTEMPTED} &
{\color{tsGrey}\fontsize{7.5pt}{9pt}\selectfont D} &
{\color{tsGrey}\fontsize{7.5pt}{9pt}\selectfont LO} &
{\color{tsGrey}\fontsize{7.5pt}{9pt}\selectfont SCAN} \\
\hline
\endfirsthead
\hline
\tsQrdHeaderStrut
{\color{tsGrey}\fontsize{7.5pt}{9pt}\selectfont Q\#} &
{\color{tsGrey}\fontsize{7.5pt}{9pt}\selectfont TOPIC} &
{\color{tsGrey}\fontsize{7.5pt}{9pt}\selectfont CONCEPT} &
{\color{tsGrey}\fontsize{7.5pt}{9pt}\selectfont ATTEMPTED} &
{\color{tsGrey}\fontsize{7.5pt}{9pt}\selectfont D} &
{\color{tsGrey}\fontsize{7.5pt}{9pt}\selectfont LO} &
{\color{tsGrey}\fontsize{7.5pt}{9pt}\selectfont SCAN} \\
\hline
\endhead
\hline
\endfoot
\hline
\endlastfoot
((*- for r in qrd_rows *))
\tsQrdRow{(((( r.number ))))}{(((( r.topic | latex_escape ))))}{(((( r.concept | latex_escape ))))}{((* if r.attempted *))Yes((* else *))No((* endif *))}{(((( r.difficulty ))))}{(((( r.learning_objective ))))}{(((( r.scan_quality | latex_escape ))))}{(((( scan_color(r.scan_quality) ))))}
((*- endfor *))
\end{longtable}
\endgroup
((* endif *))
```

### Step 5 — UI: editorial category band (accent strip + small caps)

Frontend-design call: a tinted `<tr>` background reads as "AI-generic". Better:
a thin colored **accent bar** on the left edge + small-caps label + slightly
denser line-height. The category name is the page's punctuation, not a chip.

In `web/app/app/settings/report-views/matrix.tsx`, above the `Matrix` function:

```tsx
// Category-specific accent. The strip color sells "this is a new section"
// at a glance; the row itself stays calm so checkboxes remain the focus.
// `border-l-4` gives a hairline accent strip on the left.
const CATEGORY_ACCENT: Record<string, { strip: string; label: string }> = {
  Structural:  { strip: "border-l-zinc-400",   label: "text-zinc-300" },
  Score:       { strip: "border-l-rose-500",   label: "text-rose-300" },
  Diagnostic:  { strip: "border-l-sky-500",    label: "text-sky-300" },
  Coaching:    { strip: "border-l-amber-500",  label: "text-amber-300" },
  Action:      { strip: "border-l-emerald-500",label: "text-emerald-300" },
  Quality:     { strip: "border-l-violet-500", label: "text-violet-300" },
  Engagement:  { strip: "border-l-teal-500",   label: "text-teal-300" },
};
const DEFAULT_ACCENT = { strip: "border-l-ink-30", label: "text-ink-60" };
```

In `CategoryGroup`, replace the existing `<tr className="bg-ink-5">` block:

```tsx
const a = CATEGORY_ACCENT[category] ?? DEFAULT_ACCENT;
return (
  <>
    <tr>
      <td
        colSpan={tiers.length + 1}
        className={`border-l-4 ${a.strip} bg-ink-5 pl-3 pr-2 py-2`}
      >
        <span className={`text-[11px] font-semibold uppercase tracking-[0.18em] ${a.label}`}>
          {category}
        </span>
      </td>
    </tr>
    {/* row map below */}
  </>
);
```

Why this beats a flat tint:
- The colored strip is **decisive** (4px solid) but doesn't compete with the
  data rows.
- Small caps + 0.18em tracking is a magazine convention — reads as
  "section header" without needing a big block.
- All categories use the same neutral row background — only the accent
  changes — so the eye groups by accent, not by competing tints.

### Step 6 — UI: cross-hair hover highlight

Lift hover state into `Matrix` (only place that knows both axes). In `Matrix`:

```tsx
const [hoverRow, setHoverRow] = useState<string | null>(null);
const [hoverTier, setHoverTier] = useState<string | null>(null);
```

Pass `hoverRow`, `hoverTier`, `setHoverRow`, `setHoverTier` into
`CategoryGroup`. Also tint the tier-column `<th>` when its tier is hovered:

```tsx
<th
  key={t}
  className={`px-2 text-center w-16 transition-colors duration-100
              ${hoverTier === t ? "bg-ink-10 text-ink-90" : ""}`}
  onMouseEnter={() => setHoverTier(t)}
  onMouseLeave={() => setHoverTier(null)}
>
  {t}
</th>
```

In `CategoryGroup`'s row map:

```tsx
{rows.map((row) => {
  const isRow = hoverRow === row.id;
  return (
    <tr
      key={row.id}
      className={`border-b border-ink-5 transition-colors duration-100
                  ${isRow ? "bg-ink-10" : "hover:bg-ink-5"}`}
      onMouseEnter={() => setHoverRow(row.id)}
      onMouseLeave={() => setHoverRow(null)}
    >
      <td className="px-2 py-1">…label…</td>
      {tiers.map((t) => {
        const isCol = hoverTier === t;
        // Intersection tints darker than row OR col alone.
        const cellBg = isRow && isCol
          ? "bg-ink-20"
          : (isCol ? "bg-ink-10" : "");
        return (
          <td
            key={t}
            className={`text-center transition-colors duration-100 ${cellBg}`}
            onMouseEnter={() => setHoverTier(t)}
            onMouseLeave={() => setHoverTier(null)}
          >
            <input
              type="checkbox"
              checked={checked || row.locked}
              disabled={row.locked}
              onChange={() => onToggle(t, row.id)}
              className="transition-transform duration-100 hover:scale-110"
            />
          </td>
        );
      })}
    </tr>
  );
})}
```

Result: hovering any cell —
- tints the entire row at `bg-ink-10` (one level)
- tints the entire tier column at `bg-ink-10` (one level)
- tints the intersection cell at `bg-ink-20` (one level deeper — "here it is")
- the tier header in the column tints + brightens text (`bg-ink-10 text-ink-90`)
- the checkbox itself scales 10% — tiny tactile feedback

All transitions are 100ms — fast enough to feel direct, slow enough to be
smooth. No jank.

---

## Verification

1. **Tests stay + extend green**:
   ```bash
   python3 -m pytest tests/test_report_view_config.py \
                     tests/test_report_views_store.py \
                     tests/test_report_views_api.py \
                     tests/test_render_helpers.py -v
   ```
   Expected: **25 passed** (24 existing + 1 new `scan_quality`).

2. **TypeScript clean for my files**:
   `cd web/app && npx tsc --noEmit 2>&1 | grep -E "matrix\.tsx"` — empty output.

3. **PDF render — both views**:
   ```python
   # In a Python REPL:
   import json
   from tools.generate_report import generate
   ev = json.load(open('.tmp/last_eval.json'))
   for tier in ('QA', 'WA'):
       ev['assignment']['type'] = tier
       print(tier, '->', generate(ev))
   ```
   Open both PDFs:
   - QRD spans full text width (left/right edges align with body text).
   - Header row visibly taller (~10mm) than body rows.
   - Body rows visibly taller than before (~6mm minimum).
   - SCAN column on the right, colored (green/blue/amber/red).

4. **Settings UI smoke (after API + Next restart)**:
   Open `/settings/report-views`. Confirm:
   - Each category band shows its accent strip (Diagnostic = sky,
     Coaching = amber, Action = emerald, Quality = violet, Structural =
     grey, Score = rose, Engagement = teal).
   - Small-caps label is clearly readable.
   - Hover any checkbox cell → its row + tier column tint, intersection
     deeper, tier header brightens, checkbox scales up subtly.
   - Move cursor off → all tints clear within 100ms.

5. **Grep audit** that nothing in the template references a removed macro:
   `grep -n "tsQrdRow" tools/templates/report_template.tex` — every occurrence
   passes exactly 8 args.

---

## Branching + PR

1. From clean `feat/credential-registry`:
   `git checkout -b feat/report-views-polish`
2. Apply Steps 1-6, commit (one commit is fine; split into Report / UI if
   you prefer a cleaner history).
3. Run verifications above.
4. Push: `git push -u origin feat/report-views-polish`
5. Open PR → base `feat/credential-registry`, compare
   `feat/report-views-polish`.
6. **Close PR #3 (`feat/qrd-full-width`)** with a comment linking the new PR
   — its diff is fully subsumed by Step 4 here.
7. Tidy GitHub: delete the stale merged branches `feat/report-views-renderer`
   and `feat/per-tier-report-views` if they still exist on GitHub (audit
   earlier showed they do). (Optionally enable repo Setting → General →
   "Automatically delete head branches" so future merges self-clean.)
