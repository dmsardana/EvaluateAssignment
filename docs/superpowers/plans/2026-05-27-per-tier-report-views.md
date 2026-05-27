# Per-Tier Report Views — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the operator pick which PDF report components render for each assignment tier (WA/QA/AA/GA/ZA) via a Settings UI backed by Postgres, with sensible per-tier defaults and a fallback when the DB is unreachable.

**Architecture:** A single source-of-truth catalogue in `tools/report_view_config.py` (component IDs, labels, categories, locked flags, per-tier defaults). A new `report_view_settings` Postgres table overrides defaults at runtime via a store with in-memory cache. FastAPI exposes GET/PUT/reset endpoints. The Next.js `/settings/report-views` page renders a components × tiers checkbox matrix. The Jinja LaTeX template gates every existing block plus two new blocks (DAM Matrix, QRD Table). The evaluator prompt gains three per-question fields (`concept`, `difficulty`, `learning_objective`) with safe defaults for legacy evaluations.

**Tech Stack:** Python 3 + FastAPI + psycopg (existing `tools/db.py` pool) + Postgres. Next.js (App Router) + TypeScript + fetch helpers in `web/app/lib/api.ts`. Jinja2 with custom `((* *))` delimiters + tectonic for LaTeX. Anthropic SDK (evaluator schema only).

**Scope:** Vertical slice — 18 live components (16 existing + DAM + QRD). The 14 "Proposed (default-off)" components from the spec are deferred to a follow-up plan.

---

## File Structure

**Create:**
- `tools/report_view_config.py` — catalogue, `STRUCTURAL_LOCKED`, `COMPONENT_CATALOG`, `DEFAULT_VIEWS`, `TIER_DEFAULT_VIEW`, `view_for(tier)`
- `db/migrations/002_report_view_settings.sql` — table DDL
- `web/api/services/report_views_store.py` — Postgres read/write + in-process cache + invalidation
- `web/app/app/settings/report-views/page.tsx` — page shell, data fetch, save/reset wiring
- `web/app/app/settings/report-views/matrix.tsx` — matrix UI (category-grouped rows × tier columns)
- `tests/test_report_view_config.py` — catalogue + `view_for` unit tests
- `tests/test_report_views_store.py` — store round-trip + cache invalidation
- `tests/test_report_views_api.py` — FastAPI endpoint tests (TestClient)

**Modify:**
- `tools/evaluate_pdf.py` — add 3 per-question fields to prompt schema + GUIDELINES line
- `tools/generate_report.py` — call `view_for(tier)`, expose `components` in context, add `make_dam_matrix` and `make_qrd_rows`, default missing per-question fields
- `tools/templates/report_template.tex` — wrap every existing component block in `((* if "<id>" in components *))…((* endif *))`; append DAM + QRD blocks
- `tools/templates/ts_evalreport.sty` — add `\tsDamCell` and `\tsQrdRow` macros
- `web/api/models.py` — `ReportComponentMeta`, `ReportViewsResponse`, `ReportViewsPut`, `ReportViewsResetPost`
- `web/api/routers/settings.py` — three new endpoints
- `web/app/lib/api.ts` — types + `api.reportViews()`, `api.setReportViews()`, `api.resetReportViews()`
- `web/app/components/shell.tsx` — add nav link to `/settings/report-views`
- `docs/architecture/report-structure.md` — add "Components & per-tier variants" section

Each file has one responsibility; the catalogue is the only place IDs are enumerated, and template/UI/store all import from it (indirectly via API for the UI).

---

## Task 1: Component catalogue + `view_for` (no DB yet)

**Files:**
- Create: `tools/report_view_config.py`
- Test: `tests/test_report_view_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report_view_config.py
from tools.report_view_config import (
    COMPONENT_CATALOG, DEFAULT_VIEWS, STRUCTURAL_LOCKED,
    TIER_DEFAULT_VIEW, view_for,
)


def test_structural_components_are_locked_and_in_catalog():
    for cid in STRUCTURAL_LOCKED:
        assert cid in COMPONENT_CATALOG
        assert COMPONENT_CATALOG[cid]["locked"] is True


def test_dam_and_qrd_are_in_catalog():
    assert "dam_matrix" in COMPONENT_CATALOG
    assert "qrd_table" in COMPONENT_CATALOG
    assert COMPONENT_CATALOG["dam_matrix"]["category"] == "Diagnostic"


def test_default_views_only_reference_known_ids():
    known = set(COMPONENT_CATALOG)
    for view, ids in DEFAULT_VIEWS.items():
        assert set(ids) <= known, f"{view} has unknown ids: {set(ids) - known}"


def test_view_for_returns_set_with_locked_always_included():
    for tier in ("WA", "QA", "AA", "GA", "ZA"):
        v = view_for(tier)
        assert isinstance(v, set)
        assert STRUCTURAL_LOCKED <= v, f"{tier} missing locked components"


def test_view_for_wa_uses_minimal_actionable_default():
    v = view_for("WA")
    assert "per_question_eval" not in v  # expensive, off for WA
    assert "dam_matrix" in v
    assert "qrd_table" in v


def test_view_for_qa_uses_full_default():
    v = view_for("QA")
    assert "per_question_eval" in v
    assert "rubric_matrix" in v


def test_view_for_unknown_tier_falls_back_to_minimal():
    v = view_for("XX")
    assert STRUCTURAL_LOCKED <= v
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_report_view_config.py -v`
Expected: FAIL — `ModuleNotFoundError: tools.report_view_config`.

- [ ] **Step 3: Create the catalogue module**

Create `tools/report_view_config.py`:

```python
"""Catalogue + per-tier defaults for report PDF components.

Single source of truth for which sections may render in the generated PDF.
The renderer gates every template block on membership in `view_for(tier)`.
The Settings UI reads the catalogue (via the API) to build its matrix.
"""
from __future__ import annotations

STRUCTURAL_LOCKED: set[str] = {
    "page1_header", "student_block", "score_block", "page_footer",
}

# id -> {label, description, category, locked, default_off}
COMPONENT_CATALOG: dict[str, dict] = {
    # --- Structural (locked) ---
    "page1_header":  {"label": "Header / Topic Breadcrumb", "category": "Structural",
                      "description": "Cover header with assignment + topic.",
                      "locked": True, "default_off": False},
    "student_block": {"label": "Student Block", "category": "Structural",
                      "description": "Student identity + assignment metadata.",
                      "locked": True, "default_off": False},
    "score_block":   {"label": "Score Block", "category": "Structural",
                      "description": "Overall % and band.",
                      "locked": True, "default_off": False},
    "page_footer":   {"label": "Page Footer", "category": "Structural",
                      "description": "Page numbers + branding.",
                      "locked": True, "default_off": False},

    # --- Score ---
    "attempted_note":  {"label": "Attempted-vs-Total Note", "category": "Score",
                        "description": "Renders only when attempted < total.",
                        "locked": False, "default_off": False},
    "promotion_bar":   {"label": "Promotion / Status Bar", "category": "Score",
                        "description": "Pass/fail bar against tier cutoff.",
                        "locked": False, "default_off": False},

    # --- Diagnostic ---
    "rubric_breakdown":        {"label": "Rubric Breakdown (5-dim split)",
                                "category": "Diagnostic",
                                "description": "Per-dimension averages.",
                                "locked": False, "default_off": False},
    "concept_dependency_map":  {"label": "Concept Dependency Map",
                                "category": "Diagnostic",
                                "description": "Concept graph, chunked at 25-Q blocks.",
                                "locked": False, "default_off": False},
    "dam_matrix":              {"label": "DAM (Difficulty x Learning-Objective) Matrix",
                                "category": "Diagnostic",
                                "description": "3x4 matrix of question counts + average %.",
                                "locked": False, "default_off": False},
    "qrd_table":               {"label": "QRD (Question Response Data) Table",
                                "category": "Diagnostic",
                                "description": "Q# / Topic / Concept / Attempted / Difficulty / LO.",
                                "locked": False, "default_off": False},
    "rubric_matrix":           {"label": "Summary of Rubric Matrix",
                                "category": "Diagnostic",
                                "description": "Per-question x dimension longtable.",
                                "locked": False, "default_off": False},
    "per_question_eval":       {"label": "Per-Question Evaluation",
                                "category": "Diagnostic",
                                "description": "Per-question cards. Most expensive (output tokens).",
                                "locked": False, "default_off": False},

    # --- Coaching ---
    "summary_box":     {"label": "Summary Box", "category": "Coaching",
                        "description": "Executive narrative paragraph.",
                        "locked": False, "default_off": False},
    "misconceptions":  {"label": "Misconceptual Observations", "category": "Coaching",
                        "description": "Listed misconceptions with corrections.",
                        "locked": False, "default_off": False},
    "swot_matrix":     {"label": "SWOT Matrix", "category": "Coaching",
                        "description": "Strengths / weaknesses / opportunities / threats.",
                        "locked": False, "default_off": False},
    "closing_note":    {"label": "Closing Note", "category": "Coaching",
                        "description": "Encouragement + next-sitting framing.",
                        "locked": False, "default_off": False},

    # --- Action ---
    "improvements":    {"label": "Areas of Improvement (3 priorities)",
                        "category": "Action",
                        "description": "Top three concrete action items.",
                        "locked": False, "default_off": False},

    # --- Quality ---
    "scan_overview":   {"label": "Scan Quality Overview", "category": "Quality",
                        "description": "Per-page scan issues, if any.",
                        "locked": False, "default_off": False},
    "scan_tips":       {"label": "Scanning Tips (static)", "category": "Quality",
                        "description": "Static reminders for better scans.",
                        "locked": False, "default_off": False},
}

_FULL: list[str] = [
    "page1_header", "student_block", "score_block",
    "attempted_note", "promotion_bar",
    "summary_box",
    "rubric_breakdown", "concept_dependency_map",
    "dam_matrix", "qrd_table",
    "rubric_matrix",
    "misconceptions", "swot_matrix",
    "improvements",
    "per_question_eval",
    "closing_note",
    "scan_overview", "scan_tips",
    "page_footer",
]

_MINIMAL: list[str] = [
    "page1_header", "student_block", "score_block",
    "attempted_note", "promotion_bar",
    "summary_box",
    "concept_dependency_map",
    "dam_matrix", "qrd_table",
    "swot_matrix",
    "improvements",
    "closing_note",
    "scan_overview", "scan_tips",
    "page_footer",
]

DEFAULT_VIEWS: dict[str, list[str]] = {
    "full": _FULL,
    "minimal_actionable": _MINIMAL,
}

TIER_DEFAULT_VIEW: dict[str, str] = {
    "WA": "minimal_actionable",
    "QA": "full",
    "AA": "full",
    "GA": "minimal_actionable",
    "ZA": "minimal_actionable",
}


def default_components_for(tier: str) -> list[str]:
    """Return the ordered default component list for a tier (no DB read)."""
    view_name = TIER_DEFAULT_VIEW.get(tier, "minimal_actionable")
    return list(DEFAULT_VIEWS[view_name])


def view_for(tier: str) -> set[str]:
    """Return the set of component IDs to render for `tier`.

    Reads the Postgres override if available; otherwise falls back to
    DEFAULT_VIEWS[TIER_DEFAULT_VIEW[tier]]. Locked components are always
    included even if a misconfigured row excludes them.
    """
    components: set[str] = set(default_components_for(tier))
    try:
        # Lazy import: tests for the catalogue must not require the store.
        from web.api.services.report_views_store import load as _load
        override = _load(tier)
        if override is not None:
            components = set(override)
    except Exception:
        # Store/DB unavailable -> fall back to defaults silently.
        pass
    components |= STRUCTURAL_LOCKED
    return components
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_report_view_config.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/report_view_config.py tests/test_report_view_config.py
git commit -m "feat(report): add component catalogue + per-tier view_for()"
```

---

## Task 2: Postgres table + store

**Files:**
- Create: `db/migrations/002_report_view_settings.sql`
- Create: `web/api/services/report_views_store.py`
- Test: `tests/test_report_views_store.py`

- [ ] **Step 1: Write the migration**

Create `db/migrations/002_report_view_settings.sql`:

```sql
-- db/migrations/002_report_view_settings.sql
-- Apply with:
--   docker exec -i evalassign-db psql -U evalassign -d evalassign < db/migrations/002_report_view_settings.sql
-- Idempotent.

CREATE TABLE IF NOT EXISTS report_view_settings (
    tier        TEXT PRIMARY KEY,
    components  JSONB NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- [ ] **Step 2: Apply the migration locally**

Run:
```bash
docker exec -i evalassign-db psql -U evalassign -d evalassign \
  < db/migrations/002_report_view_settings.sql
docker exec -i evalassign-db psql -U evalassign -d evalassign \
  -c "\d report_view_settings"
```
Expected: table exists with columns `tier text`, `components jsonb`, `updated_at timestamptz`.

- [ ] **Step 3: Write the failing store test**

Create `tests/test_report_views_store.py`:

```python
import os
import pytest
from web.api.services import report_views_store as store


pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="requires Postgres",
)


@pytest.fixture(autouse=True)
def _clean():
    from tools.db import execute
    execute("DELETE FROM report_view_settings WHERE tier LIKE 'TST_%'")
    store.invalidate_cache()
    yield
    execute("DELETE FROM report_view_settings WHERE tier LIKE 'TST_%'")
    store.invalidate_cache()


def test_load_returns_none_when_no_row():
    assert store.load("TST_WA") is None


def test_save_then_load_round_trip():
    store.save("TST_WA", ["page1_header", "score_block", "improvements"])
    assert store.load("TST_WA") == ["page1_header", "score_block", "improvements"]


def test_save_invalidates_cache():
    store.save("TST_WA", ["page1_header"])
    assert store.load("TST_WA") == ["page1_header"]
    store.save("TST_WA", ["page1_header", "summary_box"])
    assert store.load("TST_WA") == ["page1_header", "summary_box"]


def test_load_all_returns_dict():
    store.save("TST_WA", ["page1_header"])
    store.save("TST_QA", ["page1_header", "per_question_eval"])
    all_rows = store.load_all()
    assert all_rows["TST_WA"] == ["page1_header"]
    assert all_rows["TST_QA"] == ["page1_header", "per_question_eval"]


def test_reset_removes_row_and_returns_defaults():
    store.save("WA", ["page1_header"])  # real tier so reset has a default
    defaults = store.reset("WA")
    assert store.load("WA") is None
    assert "improvements" in defaults
```

- [ ] **Step 4: Run test to verify it fails**

Run: `DATABASE_URL=$DATABASE_URL python3 -m pytest tests/test_report_views_store.py -v`
Expected: FAIL — `ModuleNotFoundError: web.api.services.report_views_store`.

- [ ] **Step 5: Implement the store**

Create `web/api/services/report_views_store.py`:

```python
"""Read/write `report_view_settings` with an in-process cache.

The cache is invalidated on every write so a single API process always
sees its own writes; multi-process deployments accept eventual
consistency on the order of seconds since the catalogue rarely changes.
"""
from __future__ import annotations

import json
import threading
from typing import Optional

from tools.db import execute, fetch_all
from tools.report_view_config import default_components_for

_LOCK = threading.Lock()
_CACHE: dict[str, list[str]] | None = None


def invalidate_cache() -> None:
    global _CACHE
    with _LOCK:
        _CACHE = None


def _ensure_cache() -> dict[str, list[str]]:
    global _CACHE
    with _LOCK:
        if _CACHE is None:
            rows = fetch_all(
                "SELECT tier, components FROM report_view_settings"
            )
            _CACHE = {
                r["tier"]: list(r["components"])
                for r in rows
            }
        return dict(_CACHE)


def load(tier: str) -> Optional[list[str]]:
    return _ensure_cache().get(tier)


def load_all() -> dict[str, list[str]]:
    return _ensure_cache()


def save(tier: str, components: list[str]) -> None:
    payload = json.dumps(list(components))
    execute(
        """
        INSERT INTO report_view_settings (tier, components, updated_at)
        VALUES (%s, %s::jsonb, now())
        ON CONFLICT (tier) DO UPDATE
          SET components = EXCLUDED.components,
              updated_at = now()
        """,
        (tier, payload),
    )
    invalidate_cache()


def reset(tier: str) -> list[str]:
    execute("DELETE FROM report_view_settings WHERE tier = %s", (tier,))
    invalidate_cache()
    return default_components_for(tier)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `DATABASE_URL=$DATABASE_URL python3 -m pytest tests/test_report_views_store.py -v`
Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add db/migrations/002_report_view_settings.sql \
        web/api/services/report_views_store.py \
        tests/test_report_views_store.py
git commit -m "feat(api): report_view_settings table + store with cache"
```

---

## Task 3: API endpoints

**Files:**
- Modify: `web/api/models.py` (append at end of file)
- Modify: `web/api/routers/settings.py` (append three handlers)
- Test: `tests/test_report_views_api.py`

- [ ] **Step 1: Write the failing API test**

Create `tests/test_report_views_api.py`:

```python
import os
import pytest
from fastapi.testclient import TestClient
from web.api.main import app

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="requires Postgres",
)

client = TestClient(app)


def test_get_report_views_returns_catalog_and_defaults():
    r = client.get("/api/settings/report-views")
    assert r.status_code == 200
    body = r.json()
    assert set(body["tiers"]) == {"WA", "QA", "AA", "GA", "ZA"}
    ids = {c["id"] for c in body["catalog"]}
    assert {"page1_header", "dam_matrix", "qrd_table", "per_question_eval"} <= ids
    assert "page1_header" in body["by_tier"]["WA"]
    assert "per_question_eval" in body["defaults"]["QA"]


def test_put_report_views_persists_and_forces_locked():
    body = {"by_tier": {"WA": ["score_block", "improvements"]}}
    r = client.put("/api/settings/report-views", json=body)
    assert r.status_code == 200
    saved = client.get("/api/settings/report-views").json()
    assert {"page1_header", "student_block", "score_block", "page_footer"} <= set(saved["by_tier"]["WA"])
    assert "improvements" in saved["by_tier"]["WA"]


def test_put_rejects_unknown_component_id():
    body = {"by_tier": {"WA": ["not_a_real_component"]}}
    r = client.put("/api/settings/report-views", json=body)
    assert r.status_code == 422


def test_reset_restores_defaults():
    client.put("/api/settings/report-views", json={"by_tier": {"WA": ["score_block"]}})
    r = client.post("/api/settings/report-views/reset", json={"tier": "WA"})
    assert r.status_code == 200
    saved = client.get("/api/settings/report-views").json()
    assert "summary_box" in saved["by_tier"]["WA"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DATABASE_URL=$DATABASE_URL python3 -m pytest tests/test_report_views_api.py -v`
Expected: FAIL — 404 on the new routes.

- [ ] **Step 3: Add Pydantic models**

Append to `web/api/models.py`:

```python
# ---------- Report view settings ----------

class ReportComponentMeta(BaseModel):
    id: str
    label: str
    category: str
    description: str
    locked: bool = False
    default_off: bool = False


class ReportViewsResponse(BaseModel):
    tiers: list[str]
    catalog: list[ReportComponentMeta]
    by_tier: dict[str, list[str]]
    defaults: dict[str, list[str]]


class ReportViewsPut(BaseModel):
    by_tier: dict[str, list[str]]


class ReportViewsResetPost(BaseModel):
    tier: str
```

- [ ] **Step 4: Add the three handlers**

Append to `web/api/routers/settings.py` (use the same `router` already declared at the top):

```python
from fastapi import HTTPException
from tools.report_view_config import (
    COMPONENT_CATALOG, STRUCTURAL_LOCKED, TIER_DEFAULT_VIEW,
    default_components_for,
)
from web.api.services import report_views_store
from web.api.models import (
    ReportComponentMeta, ReportViewsResponse,
    ReportViewsPut, ReportViewsResetPost,
)

_TIERS: list[str] = ["WA", "QA", "AA", "GA", "ZA"]


def _catalog_payload() -> list[ReportComponentMeta]:
    return [
        ReportComponentMeta(
            id=cid,
            label=meta["label"],
            category=meta["category"],
            description=meta["description"],
            locked=meta.get("locked", False),
            default_off=meta.get("default_off", False),
        )
        for cid, meta in COMPONENT_CATALOG.items()
    ]


def _effective_by_tier() -> dict[str, list[str]]:
    overrides = report_views_store.load_all()
    out: dict[str, list[str]] = {}
    for tier in _TIERS:
        ids = overrides.get(tier) or default_components_for(tier)
        merged = list(ids)
        for loc in STRUCTURAL_LOCKED:
            if loc not in merged:
                merged.append(loc)
        out[tier] = merged
    return out


def _defaults_by_tier() -> dict[str, list[str]]:
    return {t: default_components_for(t) for t in _TIERS}


@router.get("/api/settings/report-views", response_model=ReportViewsResponse)
def get_report_views() -> ReportViewsResponse:
    return ReportViewsResponse(
        tiers=list(_TIERS),
        catalog=_catalog_payload(),
        by_tier=_effective_by_tier(),
        defaults=_defaults_by_tier(),
    )


@router.put("/api/settings/report-views", response_model=ReportViewsResponse)
def put_report_views(body: ReportViewsPut) -> ReportViewsResponse:
    known = set(COMPONENT_CATALOG)
    for tier, ids in body.by_tier.items():
        if tier not in _TIERS:
            raise HTTPException(422, f"unknown tier: {tier}")
        unknown = [i for i in ids if i not in known]
        if unknown:
            raise HTTPException(422, f"unknown component ids for {tier}: {unknown}")
        merged = list(dict.fromkeys(list(ids) + list(STRUCTURAL_LOCKED)))
        report_views_store.save(tier, merged)
    return get_report_views()


@router.post("/api/settings/report-views/reset", response_model=ReportViewsResponse)
def reset_report_views(body: ReportViewsResetPost) -> ReportViewsResponse:
    if body.tier not in _TIERS:
        raise HTTPException(422, f"unknown tier: {body.tier}")
    report_views_store.reset(body.tier)
    return get_report_views()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `DATABASE_URL=$DATABASE_URL python3 -m pytest tests/test_report_views_api.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add web/api/models.py web/api/routers/settings.py tests/test_report_views_api.py
git commit -m "feat(api): GET/PUT/reset endpoints for report-views"
```

---

## Task 4: Frontend — typed fetch helpers

**Files:**
- Modify: `web/app/lib/api.ts` (append types + three functions in the existing `api` object)

- [ ] **Step 1: Add types and helpers**

Append to `web/app/lib/api.ts` (after the existing `api.setTierCutoffs` definition; mirror the `tierCutoffs`/`setTierCutoffs` pattern):

```ts
export type ReportComponentMeta = {
  id: string;
  label: string;
  category: string;
  description: string;
  locked: boolean;
  default_off: boolean;
};

export type ReportViewsResponse = {
  tiers: string[];
  catalog: ReportComponentMeta[];
  by_tier: Record<string, string[]>;
  defaults: Record<string, string[]>;
};

export type ReportViewsPut = { by_tier: Record<string, string[]> };

// Add inside the existing `api` object:
//   reportViews:      () => jget<ReportViewsResponse>("/api/settings/report-views"),
//   setReportViews:   (body: ReportViewsPut) =>
//                        jput<ReportViewsResponse>("/api/settings/report-views", body),
//   resetReportViews: (tier: string) =>
//                        jpost<ReportViewsResponse>("/api/settings/report-views/reset", { tier }),
```

If `jpost` does not exist yet, add it next to `jput` using the same shape:

```ts
async function jpost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(API_BASE + path, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`POST ${path} -> ${r.status}`);
  return (await r.json()) as T;
}
```

- [ ] **Step 2: Type-check**

Run: `cd web/app && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/app/lib/api.ts
git commit -m "feat(web): report-views fetch helpers + types"
```

---

## Task 5: Frontend — matrix UI

**Files:**
- Create: `web/app/app/settings/report-views/page.tsx`
- Create: `web/app/app/settings/report-views/matrix.tsx`
- Modify: `web/app/components/shell.tsx` (add nav link)

- [ ] **Step 1: Create the page shell**

Create `web/app/app/settings/report-views/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { api, ReportViewsResponse } from "@/lib/api";
import { Matrix } from "./matrix";

export default function ReportViewsPage() {
  const [data, setData] = useState<ReportViewsResponse | null>(null);
  const [draft, setDraft] = useState<Record<string, string[]> | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    try {
      const r = await api.reportViews();
      setData(r);
      setDraft(r.by_tier);
    } catch (e) {
      setError(String(e));
    }
  }
  useEffect(() => { reload(); }, []);

  if (!data || !draft) return <div className="p-6">Loading…</div>;

  const dirty = JSON.stringify(draft) !== JSON.stringify(data.by_tier);

  async function save() {
    if (!draft) return;
    setSaving(true);
    try {
      const r = await api.setReportViews({ by_tier: draft });
      setData(r); setDraft(r.by_tier);
    } catch (e) { setError(String(e)); }
    finally { setSaving(false); }
  }

  async function resetTier(tier: string) {
    const r = await api.resetReportViews(tier);
    setData(r); setDraft(r.by_tier);
  }

  return (
    <div className="p-6 space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Report Components</h1>
          <p className="text-sm text-zinc-500">
            Configure which sections appear in the PDF, per tier.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            disabled={!dirty}
            onClick={() => setDraft(data.by_tier)}
            className="px-3 py-1 border rounded disabled:opacity-40"
          >Discard</button>
          <button
            disabled={!dirty || saving}
            onClick={save}
            className="px-3 py-1 rounded bg-blue-600 text-white disabled:opacity-40"
          >{saving ? "Saving…" : "Save"}</button>
        </div>
      </header>
      {error && <div className="text-red-600 text-sm">{error}</div>}
      <Matrix
        catalog={data.catalog}
        tiers={data.tiers}
        draft={draft}
        onChange={setDraft}
        onResetTier={resetTier}
      />
    </div>
  );
}
```

- [ ] **Step 2: Create the matrix component**

Create `web/app/app/settings/report-views/matrix.tsx`:

```tsx
"use client";

import { ReportComponentMeta } from "@/lib/api";

type Props = {
  catalog: ReportComponentMeta[];
  tiers: string[];
  draft: Record<string, string[]>;
  onChange: (next: Record<string, string[]>) => void;
  onResetTier: (tier: string) => void;
};

const CATEGORY_ORDER = ["Structural", "Score", "Diagnostic", "Coaching", "Action", "Quality"];

export function Matrix({ catalog, tiers, draft, onChange, onResetTier }: Props) {
  const grouped = new Map<string, ReportComponentMeta[]>();
  for (const c of catalog) {
    const list = grouped.get(c.category) ?? [];
    list.push(c);
    grouped.set(c.category, list);
  }
  const categories = CATEGORY_ORDER.filter((c) => grouped.has(c));

  function toggle(tier: string, id: string) {
    const set = new Set(draft[tier] ?? []);
    if (set.has(id)) set.delete(id); else set.add(id);
    onChange({ ...draft, [tier]: Array.from(set) });
  }

  function totals(tier: string): number {
    return (draft[tier] ?? []).length;
  }

  return (
    <table className="w-full text-sm border-collapse">
      <thead>
        <tr className="border-b">
          <th className="text-left py-2 px-2">Component</th>
          {tiers.map((t) => (
            <th key={t} className="px-2 text-center w-16">{t}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {categories.map((cat) => (
          <CategoryGroup
            key={cat}
            category={cat}
            rows={grouped.get(cat)!}
            tiers={tiers}
            draft={draft}
            onToggle={toggle}
          />
        ))}
        <tr className="border-t font-medium">
          <td className="py-2 px-2">Per-tier totals</td>
          {tiers.map((t) => (
            <td key={t} className="text-center">{totals(t)}</td>
          ))}
        </tr>
        <tr>
          <td className="py-2 px-2 text-zinc-500">Reset to defaults</td>
          {tiers.map((t) => (
            <td key={t} className="text-center">
              <button
                onClick={() => onResetTier(t)}
                className="text-xs underline text-blue-600"
              >reset</button>
            </td>
          ))}
        </tr>
      </tbody>
    </table>
  );
}

function CategoryGroup({
  category, rows, tiers, draft, onToggle,
}: {
  category: string;
  rows: ReportComponentMeta[];
  tiers: string[];
  draft: Record<string, string[]>;
  onToggle: (tier: string, id: string) => void;
}) {
  return (
    <>
      <tr className="bg-zinc-50">
        <td colSpan={tiers.length + 1} className="px-2 py-1 text-xs uppercase tracking-wide text-zinc-500">
          {category}
        </td>
      </tr>
      {rows.map((row) => (
        <tr key={row.id} className="border-b">
          <td className="px-2 py-1">
            <span title={row.description}>
              {row.locked ? "🔒 " : ""}{row.label}
            </span>
          </td>
          {tiers.map((t) => {
            const checked = (draft[t] ?? []).includes(row.id);
            return (
              <td key={t} className="text-center">
                <input
                  type="checkbox"
                  checked={checked || row.locked}
                  disabled={row.locked}
                  onChange={() => onToggle(t, row.id)}
                />
              </td>
            );
          })}
        </tr>
      ))}
    </>
  );
}
```

- [ ] **Step 3: Add nav link**

In `web/app/components/shell.tsx`, locate the settings nav list (the section that already links to `/settings/credentials`, `/settings/billing`, etc.) and add one more entry — match the exact shape of the surrounding entries:

```tsx
{ href: "/settings/report-views", label: "Report Components" },
```

- [ ] **Step 4: Run dev server and exercise it manually**

Run:
```bash
scripts/dev-api.sh &
cd web/app && npm run dev
```
Open `http://localhost:3000/settings/report-views`. Verify:
- Matrix renders with rows grouped by category.
- 🔒 rows have disabled checkboxes.
- Toggling a cell enables Save; clicking Save updates the table from the response.
- Clicking "reset" under a tier column restores defaults for that tier.

Expected: all four behaviors observed.

- [ ] **Step 5: Commit**

```bash
git add web/app/app/settings/report-views web/app/components/shell.tsx
git commit -m "feat(web): /settings/report-views matrix page"
```

---

## Task 6: Evaluator schema — 3 new per-question fields

**Files:**
- Modify: `tools/evaluate_pdf.py`

- [ ] **Step 1: Locate the per-question prompt block**

Open `tools/evaluate_pdf.py` and find the prompt section that enumerates per-question JSON fields (search for `per_question` or the dimension key list).

- [ ] **Step 2: Add the three fields to the JSON spec**

In the JSON shape inside the prompt, add to each per-question object:

```
"concept": "<short concept anchor, e.g. 'Square-root non-negativity'>",
"difficulty": "D1" | "D2" | "D3",
"learning_objective": "L1" | "L2" | "L3" | "L4"
```

- [ ] **Step 3: Add the GUIDELINES line**

In the GUIDELINES section of the same prompt, add exactly:

```
- Classify `difficulty` and `learning_objective` from the QUESTION PAPER, not from the student's response. `concept` is the single specific idea the question primarily tests.
```

- [ ] **Step 4: Run a smoke eval against an existing cached student**

Run (substitute a real cached PDF + key from `.tmp/`):
```bash
python3 tools/evaluate_pdf.py --student .tmp/<cached_student>.pdf \
                              --key .tmp/<cached_key>.pdf \
                              --out .tmp/_smoke_eval.json
python3 -c "import json; d=json.load(open('.tmp/_smoke_eval.json')); \
            q=d['questions'][0]; print(q['concept'], q['difficulty'], q['learning_objective'])"
```
Expected: a concept string + a D1/D2/D3 + an L1/L2/L3/L4 print.

- [ ] **Step 5: Commit**

```bash
git add tools/evaluate_pdf.py
git commit -m "feat(eval): per-question concept + difficulty + learning_objective"
```

---

## Task 7: Renderer — load view + DAM/QRD helpers + safe defaults

**Files:**
- Modify: `tools/generate_report.py`

- [ ] **Step 1: Import and call `view_for` in `generate()`**

In `tools/generate_report.py:generate()` (around the context-build region, lines 325–336), add near the top of the function:

```python
from tools.report_view_config import view_for
components = view_for(evaluation["assignment"]["type"])
```

and add to the context dict:

```python
"components": components,
```

- [ ] **Step 2: Add DAM helper**

In the same file, above `generate()`, add:

```python
def make_dam_matrix(evaluation: dict) -> list[list[dict]]:
    """3x4 grid (rows=D1..D3, cols=L1..L4). Each cell: {count, avg_pct}."""
    rows = ["D1", "D2", "D3"]
    cols = ["L1", "L2", "L3", "L4"]
    grid: list[list[dict]] = [
        [{"count": 0, "sum_pct": 0.0} for _ in cols] for _ in rows
    ]
    for q in evaluation.get("questions") or []:
        d = q.get("difficulty") or "D2"
        lo = q.get("learning_objective") or "L2"
        if d not in rows or lo not in cols:
            continue
        score = float(q.get("score") or 0.0)  # 0..1
        cell = grid[rows.index(d)][cols.index(lo)]
        cell["count"] += 1
        cell["sum_pct"] += 100.0 * score
    out: list[list[dict]] = []
    for r in grid:
        out.append([
            {
                "count": c["count"],
                "avg_pct": (c["sum_pct"] / c["count"]) if c["count"] else 0.0,
            }
            for c in r
        ])
    return out
```

- [ ] **Step 3: Add QRD helper**

```python
def make_qrd_rows(evaluation: dict) -> list[dict]:
    out: list[dict] = []
    for q in evaluation.get("questions") or []:
        out.append({
            "number": q.get("number"),
            "topic": q.get("topic", ""),
            "concept": q.get("concept", q.get("topic", "")),
            "attempted": bool(q.get("attempted", True)),
            "difficulty": q.get("difficulty") or "D2",
            "learning_objective": q.get("learning_objective") or "L2",
        })
    return out
```

- [ ] **Step 4: Wire helpers into the context**

In `generate()`, where the context dict is built, add:

```python
"dam_matrix": make_dam_matrix(evaluation),
"qrd_rows": make_qrd_rows(evaluation),
```

- [ ] **Step 5: Default missing fields when reading questions**

Find `questions_for_template` (or the equivalent in `generate_report.py`). Where each per-question dict is built, add defensive defaults so legacy cached evaluations still render:

```python
q.setdefault("difficulty", "D2")
q.setdefault("learning_objective", "L2")
q.setdefault("concept", q.get("topic", ""))
```

- [ ] **Step 6: Add a unit test for the helpers**

Create `tests/test_render_helpers.py`:

```python
from tools.generate_report import make_dam_matrix, make_qrd_rows


def test_dam_matrix_aggregates_counts_and_averages():
    ev = {"questions": [
        {"difficulty": "D1", "learning_objective": "L1", "score": 1.0},
        {"difficulty": "D1", "learning_objective": "L1", "score": 0.0},
        {"difficulty": "D2", "learning_objective": "L3", "score": 0.5},
    ]}
    g = make_dam_matrix(ev)
    assert g[0][0] == {"count": 2, "avg_pct": 50.0}
    assert g[1][2]["count"] == 1
    assert g[2][3] == {"count": 0, "avg_pct": 0.0}


def test_qrd_rows_apply_defaults_for_legacy_questions():
    ev = {"questions": [{"number": 1, "topic": "Quadratics"}]}
    rows = make_qrd_rows(ev)
    assert rows[0]["difficulty"] == "D2"
    assert rows[0]["learning_objective"] == "L2"
    assert rows[0]["concept"] == "Quadratics"
```

- [ ] **Step 7: Run helper tests**

Run: `python3 -m pytest tests/test_render_helpers.py -v`
Expected: 2 passed.

- [ ] **Step 8: Commit**

```bash
git add tools/generate_report.py tests/test_render_helpers.py
git commit -m "feat(report): view_for() + DAM/QRD helpers + legacy defaults"
```

---

## Task 8: Template gating + DAM/QRD blocks + sty macros

**Files:**
- Modify: `tools/templates/report_template.tex`
- Modify: `tools/templates/ts_evalreport.sty`

- [ ] **Step 1: Wrap every existing component block**

In `tools/templates/report_template.tex`, locate each of these blocks and wrap it in a Jinja gate:

```jinja
((* if "summary_box" in components *))
…existing summary box LaTeX…
((* endif *))
```

Wrap these blocks in this order (matching the existing flow in the template):

| Block | Gate ID |
|---|---|
| Cover header / topic breadcrumb | `page1_header` |
| Student identity block | `student_block` |
| Score block | `score_block` |
| Attempted-vs-total note | `attempted_note` |
| Promotion / pass-fail bar | `promotion_bar` |
| Summary narrative box | `summary_box` |
| Rubric breakdown (5-dim split) | `rubric_breakdown` |
| Concept dependency map | `concept_dependency_map` |
| Summary of rubric matrix (longtable) | `rubric_matrix` |
| Misconceptions list | `misconceptions` |
| SWOT matrix | `swot_matrix` |
| Areas of improvement (3 priorities) | `improvements` |
| Per-question evaluation cards | `per_question_eval` |
| Closing note | `closing_note` |
| Scan quality overview | `scan_overview` |
| Scanning tips | `scan_tips` |
| Page footer (only if it's a block, not a `\fancyfoot` preamble directive) | `page_footer` |

If `page_footer` is configured via `\fancyfoot` in the preamble rather than inline, leave it always-on (it's locked anyway).

- [ ] **Step 2: Add DAM matrix block**

Append after the `concept_dependency_map` block:

```jinja
((* if "dam_matrix" in components *))
\section*{Difficulty × Learning-Objective Matrix}
\begin{tabular}{l|cccc}
\toprule
 & L1 Recall & L2 Apply & L3 Analyse & L4 Create \\
\midrule
((* for label, row in [("D1 Easy", dam_matrix[0]), ("D2 Medium", dam_matrix[1]), ("D3 Difficult", dam_matrix[2])] *))
(((( label )))) ((* for cell in row *)) & \tsDamCell{(((( cell.count ))))}{(((( "%.0f"|format(cell.avg_pct) ))))} ((* endfor *)) \\
((* endfor *))
\bottomrule
\end{tabular}
((* endif *))
```

- [ ] **Step 3: Add QRD table block**

Append after the DAM block:

```jinja
((* if "qrd_table" in components *))
\section*{Question Response Data}
\begin{longtable}{rlllccc}
\toprule
Q\# & Topic & Concept & Attempted & D & LO \\
\midrule
((* for r in qrd_rows *))
\tsQrdRow{(((( r.number ))))}{(((( r.topic|tex ))))}{(((( r.concept|tex ))))}{((* if r.attempted *))Yes((* else *))No((* endif *))}{(((( r.difficulty ))))}{(((( r.learning_objective ))))}
((* endfor *))
\bottomrule
\end{longtable}
((* endif *))
```

- [ ] **Step 4: Add the two `\ts*` macros**

Append to `tools/templates/ts_evalreport.sty`:

```latex
% --- DAM cell: count + average % ---
% \tsDamCell{count}{avg_pct_int}
\newcommand{\tsDamCell}[2]{%
  \ifnum#1=0\relax
    {\color{black!40}\,0\,}%
  \else
    \makebox[1.6cm][c]{#1\,/\,#2\%}%
  \fi
}

% --- QRD row: 6 columns ---
% \tsQrdRow{number}{topic}{concept}{attempted}{difficulty}{lo}
\newcommand{\tsQrdRow}[6]{#1 & #2 & #3 & #4 & #5 & #6 \\}
```

- [ ] **Step 5: Render an existing cached eval end-to-end**

Pick a recent cached evaluation JSON under `.tmp/` and render:

```bash
python3 tools/generate_report.py \
  --evaluation .tmp/<cached>_eval.json \
  --out .tmp/_smoke_report.pdf
ls -la .tmp/_smoke_report.pdf
```

Expected: PDF produced; open it and confirm the DAM and QRD sections appear for tiers whose default view includes them (WA/GA/ZA), and QA/AA still renders per-question evaluation cards.

- [ ] **Step 6: Grep audit — no orphan gates**

Run:
```bash
grep -oE '"[a-z_]+" in components' tools/templates/report_template.tex | sort -u
```
Confirm every ID in the output appears in `tools/report_view_config.COMPONENT_CATALOG`. No typos, no orphans.

- [ ] **Step 7: Commit**

```bash
git add tools/templates/report_template.tex tools/templates/ts_evalreport.sty
git commit -m "feat(report): gate template blocks by view + DAM/QRD sections"
```

---

## Task 9: End-to-end verification

- [ ] **Step 1: Toggle WA via the UI and re-render**

In the UI at `/settings/report-views`, uncheck `per_question_eval` and `rubric_matrix` for WA, click Save. Then render a WA cached eval:

```bash
python3 tools/generate_report.py --evaluation .tmp/<wa_cached>_eval.json --out .tmp/_wa_after.pdf
```

Expected: PDF has no per-question evaluation cards or rubric-matrix longtable, but does have DAM, QRD, SWOT, improvements, closing note.

- [ ] **Step 2: Reset WA and re-render**

In the UI, click "reset" under the WA column. Re-render the same eval. Expected: defaults restored, output matches the minimal_actionable layout.

- [ ] **Step 3: Run the full test suite**

Run: `DATABASE_URL=$DATABASE_URL python3 -m pytest tests/ -v`
Expected: all new tests pass; no regressions.

- [ ] **Step 4: Update docs**

In `docs/architecture/report-structure.md`, add a "Components & per-tier variants" section that:
- Links to `tools/report_view_config.py` as the source of truth.
- Names the API endpoints.
- Notes the locked-rows policy and DB fallback.

- [ ] **Step 5: Final commit**

```bash
git add docs/architecture/report-structure.md
git commit -m "docs(report): document per-tier view settings"
```

---

## Self-Review

**Spec coverage:**
- A. Catalogue → Task 1.
- B. Postgres table + store + API + Pydantic models → Tasks 2, 3.
- C. Frontend Settings page (matrix, save, reset, dirty indicator) → Tasks 4, 5. (Cost preview deferred — see below.)
- D. Renderer integration (`view_for`, helpers, defaults) → Task 7.
- E. Evaluator changes (3 new fields + guideline) → Task 6.
- F. Files modified/created → covered across tasks; matches "File Structure" header.
- G. Verification → Task 9.

**Deferred from spec (explicit in scope statement):**
- 14 proposed default-off components and their template stubs.
- Cost-preview row in the matrix (needs a per-component token-estimate table; nothing in the codebase to wire into yet — values would be guessed).
- Per-tier collapsible category headings (matrix groups by category but uses sticky headings rather than collapse animation).

**Placeholder scan:** No "TBD" / "implement later" / "appropriate error handling" — every step has either code, an exact command, or a precise file pointer.

**Type consistency:**
- `view_for()` returns `set[str]`; template uses `"<id>" in components` which works for sets.
- `report_views_store.save(tier, components)` parameter names match call sites in `settings.py`.
- API `by_tier: dict[str, list[str]]` matches `ReportViewsPut` and the TS `Record<string, string[]>`.
- `make_dam_matrix` returns `list[list[dict]]` indexed `[row][col]`; template indexes `dam_matrix[0..2]` and iterates `row` — consistent.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-27-per-tier-report-views.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task with two-stage review.

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch with checkpoints.

**Which approach?**
