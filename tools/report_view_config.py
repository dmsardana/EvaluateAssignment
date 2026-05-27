"""Per-tier report variants — single source of truth.

Every report rendering reads `view_for(tier) -> set[component_id]` and
the template gates each component with `{% if "<id>" in components %}`.

Phase 1 (this file alone) ships fixed defaults per tier. Phase 2 layers
a Postgres-backed override store on top via `register_override_loader()`.
"""
from __future__ import annotations

import os
from typing import Callable

# IDs that must always render — checkbox is locked-on in the Settings UI.
STRUCTURAL_LOCKED: frozenset[str] = frozenset({
    "page1_header", "student_block", "score_block", "page_footer",
})

# Component catalogue.
# Each entry: id -> {label, category, description, default_off}.
# `default_off` is for proposed components that ship as stubs and
# appear in the Settings UI for opt-in but aren't in any preset view.
COMPONENT_CATALOG: dict[str, dict] = {
    # Structural (locked)
    "page1_header":           {"label": "Header / Topic Breadcrumb",  "category": "Structural", "description": "Page chrome with topic path + tier label.",                         "default_off": False},
    "student_block":          {"label": "Student Block",              "category": "Structural", "description": "Name / Assignment / Topic / Date strip on page 1.",                 "default_off": False},
    "score_block":            {"label": "Score Block",                "category": "Structural", "description": "Big score panel: percentage, earned/max, band, verdict.",           "default_off": False},
    "page_footer":            {"label": "Page Footer",                "category": "Structural", "description": "Footer strip on every page.",                                       "default_off": False},
    # Score
    "attempted_note":         {"label": "Attempted-vs-Total Note",    "category": "Score",      "description": "Surfaces denominator when student didn't attempt every question.",  "default_off": False},
    "promotion_bar":          {"label": "Promotion / Status Bar",     "category": "Score",      "description": "Tier-promotion outcome + threshold note.",                          "default_off": False},
    # Coaching
    "summary_box":            {"label": "Summary Box",                "category": "Coaching",   "description": "3-4 sentence plain-language summary aimed at parents/admin.",       "default_off": False},
    "misconceptions":         {"label": "Misconceptual Observations", "category": "Coaching",   "description": "Wrong-vs-correct mental model for each conceptual gap.",            "default_off": False},
    "swot_matrix":            {"label": "SWOT Matrix",                "category": "Coaching",   "description": "Strengths, Weaknesses, Opportunities, Threats — anchored to Q-numbers.", "default_off": False},
    "closing_note":           {"label": "Closing Note",               "category": "Coaching",   "description": "Intro + what_signals + 3 next-step bullets.",                       "default_off": False},
    # Diagnostic
    "rubric_breakdown":       {"label": "Rubric Breakdown (5-dim)",   "category": "Diagnostic", "description": "Aggregate split-bar + 5-row table (CU 40 / AM 20 / SS 20 / NA 10 / PR 10).", "default_off": False},
    "concept_dependency_map": {"label": "Concept Dependency Map",     "category": "Diagnostic", "description": "Concept × Question heat-map (G/A/R/N cells). Chunked at 25-Q blocks.", "default_off": False},
    "dam_matrix":             {"label": "DAM Matrix (Difficulty × LO)", "category": "Diagnostic", "description": "3 difficulty rows × 4 learning-objective columns. Counts + avg performance per bucket.", "default_off": False},
    "qrd_table":              {"label": "QRD Table (Question Response Data)", "category": "Diagnostic", "description": "Per-question: Topic · Concept · Attempted · Difficulty · Learning Objective.", "default_off": False},
    "rubric_matrix":          {"label": "Summary of Rubric Matrix",   "category": "Diagnostic", "description": "Per-question × 5 dimensions + average. Sorted weakest first.",      "default_off": False},
    "per_question_eval":      {"label": "Per-Question Evaluation",    "category": "Diagnostic", "description": "Deep card per question with working, feedback, dimension cells. Highest token cost.", "default_off": False},
    # Action
    "improvements":           {"label": "Areas of Improvement",       "category": "Action",     "description": "Exactly 3 ranked priorities (Critical / Important / Nice-to-have).", "default_off": False},
    # Quality
    "scan_overview":          {"label": "Scan Quality Overview",      "category": "Quality",    "description": "Per-question Excellent/Good/Acceptable/Poor breakdown.",            "default_off": False},
    "scan_tips":              {"label": "Scanning Tips",              "category": "Quality",    "description": "Static checklist for the student's next submission.",               "default_off": False},
    # Proposed (default-OFF) — opt-in via Settings UI
    "parent_note":            {"label": "Parent Note",                "category": "Engagement", "description": "2-3 plain-English sentences specifically addressed to parents.",   "default_off": True},
    "topic_mastery_history":  {"label": "Topic Mastery Tracker",      "category": "Diagnostic", "description": "This sitting vs the student's previous attempts in the same topic.", "default_off": True},
    "peer_benchmark":         {"label": "Peer Benchmark Bar",         "category": "Diagnostic", "description": "Anonymised class distribution with this student's marker.",         "default_off": True},
    "time_budget":            {"label": "Suggested Time Budget",      "category": "Action",     "description": "Per-topic minutes for next sitting — turns the report into a study plan.", "default_off": True},
    "prerequisite_chain":     {"label": "Concept Prerequisite Chain", "category": "Coaching",   "description": "For the weakest concept, points to the foundational topic to revisit first.", "default_off": True},
    "quick_win":              {"label": "Quick Win Box",              "category": "Action",     "description": "The single habit fix worth ~5% — sharper than the 3-priority Areas.", "default_off": True},
    "common_pitfalls":        {"label": "Common-Pitfall Spotter",     "category": "Coaching",   "description": "Misconceptions rewritten in student-friendly language.",            "default_off": True},
    "reattempt_worksheet":    {"label": "Reattempt Worksheet",        "category": "Action",     "description": "3-5 auto-picked practice questions at the right D/LO for next sitting.", "default_off": True},
    "daily_routine":          {"label": "5-Day Daily Routine",        "category": "Action",     "description": "Concrete 15-min/day prescription for the week ahead.",              "default_off": True},
    "glossary":               {"label": "Glossary of Misused Terms",  "category": "Coaching",   "description": "4-6 entries: terms the student misused, with corrections.",         "default_off": True},
    "encouragement":          {"label": "Encouragement / Streaks",    "category": "Engagement", "description": "Visual stickers for things done right — for younger / lower-tier students.", "default_off": True},
    "effort_outcome":         {"label": "Effort-vs-Outcome plot",     "category": "Diagnostic", "description": "Working-density vs accuracy — detects rushed vs thorough.",         "default_off": True},
    "since_last_attempt":     {"label": "What Changed Since Last Attempt", "category": "Diagnostic", "description": "On re-attempts: which concepts improved / regressed.",        "default_off": True},
    "qr_lecture":             {"label": "QR to Re-watch Lecture",     "category": "Engagement", "description": "Mobile-friendly QR linking to the relevant explainer video.",       "default_off": True},
}

KNOWN_COMPONENT_IDS: frozenset[str] = frozenset(COMPONENT_CATALOG.keys())

DEFAULT_VIEWS: dict[str, list[str]] = {
    "full": [
        "page1_header", "student_block", "score_block", "page_footer",
        "attempted_note", "promotion_bar", "summary_box",
        "rubric_breakdown",
        "concept_dependency_map",
        "rubric_matrix",
        "misconceptions",
        "swot_matrix",
        "improvements",
        "per_question_eval",
        "closing_note",
        "scan_overview",
        "scan_tips",
    ],
    "minimal_actionable": [
        "page1_header", "student_block", "score_block", "page_footer",
        "attempted_note",
        "summary_box",
        "concept_dependency_map",
        "dam_matrix",
        "qrd_table",
        "swot_matrix",
        "improvements",
        "closing_note",
    ],
}

TIER_DEFAULT_VIEW: dict[str, str] = {
    "WA": "minimal_actionable",
    "QA": "full",
    "AA": "full",
    "GA": "minimal_actionable",
    "ZA": "minimal_actionable",
}


# Phase-2 hook: report_views_store will call register_override_loader
# with a function that returns the per-tier persisted list (or None).
_override_loader: Callable[[str], list[str] | None] | None = None


def register_override_loader(fn: Callable[[str], list[str] | None]) -> None:
    global _override_loader
    _override_loader = fn


def _resolve_default(tier: str) -> list[str]:
    preset = TIER_DEFAULT_VIEW.get(tier.upper(), "full")
    env_override = os.environ.get(f"REPORT_VIEW_{tier.upper()}", "").strip()
    if env_override in DEFAULT_VIEWS:
        preset = env_override
    return list(DEFAULT_VIEWS.get(preset, DEFAULT_VIEWS["full"]))


def view_for(tier: str) -> set[str]:
    """Return the set of component IDs to render for this tier."""
    tier_u = (tier or "").upper()
    components: list[str] | None = None
    if _override_loader is not None:
        try:
            components = _override_loader(tier_u)
        except Exception:
            components = None
    if components is None:
        components = _resolve_default(tier_u)
    out = {c for c in components if c in KNOWN_COMPONENT_IDS}
    out.update(STRUCTURAL_LOCKED)
    return out


def defaults_for(tier: str) -> list[str]:
    """Used by the Settings UI / reset endpoint."""
    return _resolve_default(tier)
