# Per-tier report variants + Settings UI to configure them

## Context
Today every assignment tier (WA / QA / AA / GA / ZA) renders the same
16-component PDF. The operator wants two things:

1. **Different defaults per tier** — full report for high-stakes tiers
   (QA, AA), a minimal-actionable variant for lower-stakes ones (WA,
   GA, ZA) that costs less and reads faster.
2. **A Settings page** to choose, per tier, which components to
   include — a matrix of components × tiers with checkboxes. Operator
   can rebalance any time without code changes.

Two **new** components are explicitly requested:

- **DAM Matrix** — 3 rows × 4 columns
  - Rows: D1 Easy · D2 Medium · D3 Difficult
  - Cols: L1 Recall · L2 Apply · L3 Relate/Analytical · L4 Create/Synthesise
  - Each cell: question count + average %; cell colour by avg.
- **QRD Table** — Q# · Topic · Concept · Attempted · Difficulty · LO

These need three new per-question JSON fields from the evaluator:
`difficulty` (D1/D2/D3), `learning_objective` (L1–L4), `concept`.

**Decisions captured up-front (asked & answered):**
- **Structural rows are locked** — Header, Student Block, Score Block,
  Page Footer always render. Checkboxes hidden/disabled for those rows.
- **Storage: Postgres** — new table `report_view_settings` for per-tier
  component lists, mirroring how scores live in Postgres today.

---

## Architecture overview

```
[Settings UI]                  [Postgres]              [Report renderer]
  matrix of checkboxes  ──PUT──►  report_view_       ◄──read at render time
  per-tier component         │    settings(tier, ──── tools/report_view_
  toggles + cost preview     │    components)        │   config.py
                             │                       │
                             └── falls back to ──────┘
                                 DEFAULT_VIEWS if
                                 row missing
```

Every report generation calls `view_for(tier)` →
`{components: set[str]}` → template renders only those.

---

## A. Component catalogue (single source of truth)

New module **`tools/report_view_config.py`** with:

```python
STRUCTURAL_LOCKED = {"page1_header", "student_block",
                     "score_block", "page_footer"}  # always render

# id -> {label, description, category, default_off}
COMPONENT_CATALOG: dict[str, dict] = { ... }    # see table below

DEFAULT_VIEWS: dict[str, list[str]] = {
    "full":               [ ...16 existing + dam_matrix + qrd_table ... ],
    "minimal_actionable": [ ...page1 + concept_map + dam + qrd + swot + improvements + closing_note ... ],
}

TIER_DEFAULT_VIEW = {
    "WA": "minimal_actionable",
    "QA": "full",
    "AA": "full",
    "GA": "minimal_actionable",
    "ZA": "minimal_actionable",
}

def view_for(tier: str) -> set[str]: ...
# reads Postgres first, falls back to DEFAULT_VIEWS[TIER_DEFAULT_VIEW[tier]]
```

### Catalogue contents (each row = one toggleable component)

**Currently rendered (locked or default-on):**

| ID | Label | Category | Notes |
|---|---|---|---|
| `page1_header` | Header / Topic Breadcrumb | Structural | **Locked** |
| `student_block` | Student Block | Structural | **Locked** |
| `score_block` | Score Block | Structural | **Locked** |
| `page_footer` | Page Footer | Structural | **Locked** |
| `attempted_note` | Attempted-vs-Total Note | Score | Conditional already (renders only when attempted<total) |
| `promotion_bar` | Promotion / Status Bar | Score | |
| `summary_box` | Summary Box (exec narrative) | Coaching | |
| `rubric_breakdown` | Rubric Breakdown (5-dim split) | Diagnostic | |
| `concept_dependency_map` | Concept Dependency Map | Diagnostic | Chunked at 25-Q blocks |
| `rubric_matrix` | Summary of Rubric Matrix | Diagnostic | longtable, per-Q × dims |
| `misconceptions` | Misconceptual Observations | Coaching | |
| `swot_matrix` | SWOT Matrix | Coaching | |
| `improvements` | Areas of Improvement (3 priorities) | Action | |
| `per_question_eval` | Per-Question Evaluation cards | Diagnostic | **Most expensive** (output tokens) |
| `closing_note` | Closing Note | Coaching | |
| `scan_overview` | Scan Quality Overview | Quality | |
| `scan_tips` | Scanning Tips (static) | Quality | |

**New components requested:**

| ID | Label | Category | Default |
|---|---|---|---|
| `dam_matrix` | DAM (Difficulty × Learning-Objective) Matrix | Diagnostic | on for WA/GA/ZA |
| `qrd_table` | QRD (Question Response Data) Table | Diagnostic | on for WA/GA/ZA |

**Proposed new components (default-OFF, surfaced in catalogue for opt-in)** — useful for student/parents:

| ID | Label | Category | Why it helps student/parent |
|---|---|---|---|
| `parent_note` | Parent Note | Engagement | 2-3 plain-English sentences for parents, zero jargon |
| `topic_mastery_history` | Topic Mastery Tracker | Diagnostic | This sitting vs the student's previous attempts on the same topic |
| `peer_benchmark` | Peer Benchmark Bar | Diagnostic | Anonymised class distribution + this student's marker |
| `time_budget` | Suggested Time Budget | Action | Per-topic minutes for next sitting → study plan |
| `prerequisite_chain` | Concept Prerequisite Chain | Coaching | For weakest concept, points to the foundational topic to revisit first |
| `quick_win` | Quick Win Box | Action | The single habit fix worth ~5% — sharper than the 3-priority Areas |
| `common_pitfalls` | Common-Pitfall Spotter | Coaching | Misconceptions rewritten in student-friendly language |
| `reattempt_worksheet` | Reattempt Worksheet | Action | 3-5 auto-picked practice questions at the right D/LO for next sitting |
| `daily_routine` | 5-Day Daily Routine | Action | Concrete 15-min/day prescription for the week ahead |
| `glossary` | Glossary of Misused Terms | Coaching | 4-6 entries the student got wrong in working |
| `encouragement` | Encouragement / Streaks | Engagement | Younger / lower-tier — visual stickers for things done right |
| `effort_outcome` | Effort-vs-Outcome plot | Diagnostic | Working-density vs accuracy — detects "rushed" vs "thorough" |
| `since_last_attempt` | What Changed Since Last Attempt | Diagnostic | On re-attempts; shows improved/regressed concepts |
| `qr_lecture` | QR to Re-watch Lecture | Engagement | If lecture videos exist, mobile-friendly link |

> Proposed components ship as **stubs** (catalogue entry + empty template
> block + helper that returns empty data). The toggle exists so the
> operator can plan rollouts. Each becomes "live" when its data
> source is wired up — separate follow-up tickets, not this plan.

---

## B. Backend — Postgres + API

### New table

```sql
CREATE TABLE report_view_settings (
    tier        TEXT PRIMARY KEY,        -- 'WA', 'QA', 'AA', 'GA', 'ZA', …
    components  JSONB NOT NULL,          -- ordered list of component IDs
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Migration: add to whichever Alembic / SQL-migrations location the repo
already uses (or a simple `web/api/db/migrations/00X_report_views.sql`
if migrations are hand-managed).

### New service — `web/api/services/report_views_store.py`

```python
def load_all() -> dict[str, list[str]]: ...
def load(tier: str) -> list[str] | None: ...
def save(tier: str, components: list[str]) -> None: ...
def reset(tier: str) -> list[str]:   # restores DEFAULT_VIEWS for that tier
```

In-memory cache + invalidate-on-save. `tools/report_view_config.view_for`
reads through this; falls back to defaults if the DB is unreachable.

### New router endpoints — `web/api/routers/settings.py`

| Method | Path | Body / Response |
|---|---|---|
| `GET`  | `/api/settings/report-views` | `{tiers: [WA,QA,…], catalog: [{id,label,category,description,locked,default_off}], by_tier: {WA: [ids…], …}, defaults: {WA: [ids…], …}}` |
| `PUT`  | `/api/settings/report-views` | body `{by_tier: {WA: [ids…], …}}` → validates IDs against catalog, locked rows force-included, writes to Postgres, invalidates cache |
| `POST` | `/api/settings/report-views/reset` | body `{tier: "WA"}` → restores `DEFAULT_VIEWS[TIER_DEFAULT_VIEW[tier]]` |

Pydantic models added to `web/api/models.py`:

```python
class ReportComponentMeta(BaseModel):
    id: str; label: str; category: str
    description: str; locked: bool = False
    default_off: bool = False

class ReportViewsResponse(BaseModel):
    tiers: list[str]
    catalog: list[ReportComponentMeta]
    by_tier: dict[str, list[str]]
    defaults: dict[str, list[str]]

class ReportViewsPut(BaseModel):
    by_tier: dict[str, list[str]]
```

---

## C. Frontend — Settings page

### Route

`/settings/report-views` — new page at
`web/app/app/settings/report-views/page.tsx`. Linked from the existing
settings index (or `/settings` nav) — add a card "Report Components".

### Layout

```
┌──────────────────────────────────────────────────────────────────┐
│  Report Components                                 [Save] [Reset]│
│  Configure which sections appear in the PDF, per tier.           │
│                                                                  │
│                                ┌────┬────┬────┬────┬────┐        │
│  Component                     │ WA │ QA │ AA │ GA │ ZA │        │
│  ──────────────────────────────┼────┼────┼────┼────┼────┤        │
│  🔒 Header                      │ ✓  │ ✓  │ ✓  │ ✓  │ ✓  │ locked │
│  🔒 Student Block               │ ✓  │ ✓  │ ✓  │ ✓  │ ✓  │ locked │
│  🔒 Score Block                 │ ✓  │ ✓  │ ✓  │ ✓  │ ✓  │ locked │
│  🔒 Page Footer                 │ ✓  │ ✓  │ ✓  │ ✓  │ ✓  │ locked │
│  ▼ Score                                                         │
│    Promotion / Status Bar      │ ☐  │ ☑  │ ☑  │ ☐  │ ☐  │        │
│    Attempted-vs-Total Note     │ ☑  │ ☑  │ ☑  │ ☑  │ ☑  │        │
│  ▼ Diagnostic                                                    │
│    Rubric Breakdown            │ ☐  │ ☑  │ ☑  │ ☐  │ ☐  │        │
│    Concept Dependency Map      │ ☑  │ ☑  │ ☑  │ ☑  │ ☑  │        │
│    DAM Matrix (new)            │ ☑  │ ☐  │ ☐  │ ☑  │ ☑  │        │
│    QRD Table (new)             │ ☑  │ ☐  │ ☐  │ ☑  │ ☑  │        │
│    Summary of Rubric Matrix    │ ☐  │ ☑  │ ☑  │ ☐  │ ☐  │        │
│    Per-Question Evaluation $$$ │ ☐  │ ☑  │ ☑  │ ☐  │ ☐  │        │
│  ▼ Coaching                                                      │
│    Summary Box                 │ ☑  │ ☑  │ ☑  │ ☑  │ ☑  │        │
│    Misconceptual Observations  │ ☐  │ ☑  │ ☑  │ ☐  │ ☐  │        │
│    SWOT Matrix                 │ ☑  │ ☑  │ ☑  │ ☑  │ ☑  │        │
│    Closing Note                │ ☑  │ ☑  │ ☑  │ ☑  │ ☑  │        │
│  ▼ Action                                                        │
│    Areas of Improvement        │ ☑  │ ☑  │ ☑  │ ☑  │ ☑  │        │
│  ▼ Quality                                                       │
│    Scan Quality Overview       │ ☑  │ ☑  │ ☑  │ ☑  │ ☑  │        │
│    Scanning Tips               │ ☑  │ ☐  │ ☐  │ ☑  │ ☑  │        │
│  ▼ Proposed (default off)                                        │
│    Parent Note                 │ ☐  │ ☐  │ ☐  │ ☐  │ ☐  │        │
│    Topic Mastery Tracker       │ ☐  │ ☐  │ ☐  │ ☐  │ ☐  │        │
│    Peer Benchmark Bar          │ ☐  │ ☐  │ ☐  │ ☐  │ ☐  │        │
│    Suggested Time Budget       │ ☐  │ ☐  │ ☐  │ ☐  │ ☐  │        │
│    Concept Prerequisite Chain  │ ☐  │ ☐  │ ☐  │ ☐  │ ☐  │        │
│    Quick Win Box               │ ☐  │ ☐  │ ☐  │ ☐  │ ☐  │        │
│    Common-Pitfall Spotter      │ ☐  │ ☐  │ ☐  │ ☐  │ ☐  │        │
│    Reattempt Worksheet         │ ☐  │ ☐  │ ☐  │ ☐  │ ☐  │        │
│    5-Day Daily Routine         │ ☐  │ ☐  │ ☐  │ ☐  │ ☐  │        │
│    Glossary of Misused Terms   │ ☐  │ ☐  │ ☐  │ ☐  │ ☐  │        │
│    Encouragement / Streaks     │ ☐  │ ☐  │ ☐  │ ☐  │ ☐  │        │
│    Effort-vs-Outcome plot      │ ☐  │ ☐  │ ☐  │ ☐  │ ☐  │        │
│    What Changed Since Last     │ ☐  │ ☐  │ ☐  │ ☐  │ ☐  │        │
│    QR to Re-watch Lecture      │ ☐  │ ☐  │ ☐  │ ☐  │ ☐  │        │
│                                                                  │
│   Per-tier totals →            │ 11 │ 14 │ 14 │ 11 │ 11 │        │
│   Est. cost (Sonnet 4.6)       │$.14│$.25│$.25│$.14│$.14│        │
└──────────────────────────────────────────────────────────────────┘
```

### Interaction

- **Rows grouped by category** with collapsible section headings.
- **Tooltip on each component label** → its `description` from the catalog.
- **Locked rows**: 🔒 icon + disabled checkbox (always checked).
- **Click checkbox** → optimistic local-state update; nothing persisted
  until Save.
- **Save** → PUT `/api/settings/report-views`. Toast + invalidate SWR.
- **Reset** (per-column or whole-table) → POST reset endpoint;
  reloads selection from `defaults`.
- **Cost estimate**: client-side, derived from the catalogue
  (rough output-token estimate per component × Sonnet 4.6 rate). Pulled
  from a small constant table for now; later wire to actual usage stats.
- **Dirty indicator**: Save button highlighted when local state diverges
  from server state; "Discard" button visible.

### Component files

- `web/app/app/settings/report-views/page.tsx` — page shell + data fetch
- `web/app/app/settings/report-views/matrix.tsx` — the matrix table
- `web/app/lib/api/report-views.ts` — typed fetch helpers
- Reuses existing `Card`, `Toast`, `Button` primitives.

---

## D. Renderer integration

`tools/generate_report.py:generate()`:

```python
from tools.report_view_config import view_for
components = view_for(evaluation["assignment"]["type"])  # set[str]
context["components"] = components
```

`tools/templates/report_template.tex`: every existing component block
gets wrapped in `((* if "<id>" in components *))…((* endif *))`. Add
two new blocks for `dam_matrix` and `qrd_table`, plus 14 stub blocks
for proposed components (each currently emits nothing or a single
"coming soon" line gated by an additional `((* if X is defined *))`).

Helpers in `generate_report.py`:
- `make_dam_helper(evaluation)` → returns callable for the 3×4 cell.
- `make_qrd_rows(evaluation)` → returns flat list of dicts ready for
  template iteration.

---

## E. Evaluator changes — `tools/evaluate_pdf.py`

Prompt schema adds three per-question fields:
- `concept: str` — short concept anchor (e.g. "Square-root non-negativity")
- `difficulty: "D1"|"D2"|"D3"`
- `learning_objective: "L1"|"L2"|"L3"|"L4"`

Plus a GUIDELINES line: classify these from the **question paper**, not
from the student's response.

Defensive defaults in
`generate_report.py:questions_for_template` for cached evals that lack
the fields: `D2` / `L2` / `q.topic`. So old reports re-render without
re-evaluation; force re-eval to populate real classifications.

---

## F. Files modified / created

NEW:
- `tools/report_view_config.py` — catalogue, defaults, `view_for()`
- `web/api/services/report_views_store.py` — Postgres read/write + cache
- `web/api/db/migrations/00X_report_views.sql` (or equivalent) — table DDL
- `tools/templates/components/` (if we choose to extract; can defer)
- `web/app/app/settings/report-views/page.tsx`
- `web/app/app/settings/report-views/matrix.tsx`
- `web/app/lib/api/report-views.ts`

CHANGED:
- `tools/evaluate_pdf.py` — prompt schema (3 new per-question fields)
- `tools/generate_report.py` — load view, set `components`, DAM/QRD helpers, defaults
- `tools/templates/report_template.tex` — gate every block; add DAM + QRD blocks; stubs for proposed
- `tools/templates/ts_evalreport.sty` — `\tsDamCell`, `\tsQrdRow` macros
- `web/api/models.py` — `ReportComponentMeta`, `ReportViewsResponse`, `ReportViewsPut`
- `web/api/routers/settings.py` — new endpoints
- `web/app/lib/api.ts` — type for `ReportComponentMeta` etc.
- `web/app/app/settings/page.tsx` (or nav) — link to /settings/report-views
- `docs/architecture/report-structure.md` — inventory + variants + settings page section

---

## G. Verification

1. **DB migration runs**: confirm `report_view_settings` table exists.
2. **API**: `curl /api/settings/report-views` returns full catalog +
   default `by_tier` map; `PUT` round-trips; `POST reset` restores defaults.
3. **UI**: open `/settings/report-views`, toggle a few cells, Save,
   refresh — selection persists.
4. **Cost preview** updates live as cells toggle.
5. **Render QA submission** → unchanged (full layout matches today).
6. **Render GA submission** → only the configured components appear;
   `.tmp/_usage/<today>.jsonl` shows ~30–40% lower `cost_usd_est`.
7. **Force-toggle a proposed stub** (e.g. `parent_note`) ON for QA →
   PDF builds without error; section renders empty/placeholder.
8. **Old cached eval** (no D/LO/concept) re-renders end-to-end with
   defaults (D2/L2/q.topic) — DAM cells show neutral counts, QRD shows
   defaulted values.
9. Grep `((* if "` in `report_template.tex` → every gated ID is in the
   catalogue (no orphans, no typos).
