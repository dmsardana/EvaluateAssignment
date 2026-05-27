from tools.report_view_config import (
    COMPONENT_CATALOG, DEFAULT_VIEWS, KNOWN_COMPONENT_IDS,
    STRUCTURAL_LOCKED, TIER_DEFAULT_VIEW, defaults_for, view_for,
)


def test_structural_components_present_in_catalog():
    for cid in STRUCTURAL_LOCKED:
        assert cid in COMPONENT_CATALOG


def test_dam_and_qrd_are_in_catalog():
    assert "dam_matrix" in COMPONENT_CATALOG
    assert "qrd_table" in COMPONENT_CATALOG
    assert COMPONENT_CATALOG["dam_matrix"]["category"] == "Diagnostic"


def test_default_views_only_reference_known_ids():
    for view, ids in DEFAULT_VIEWS.items():
        assert set(ids) <= KNOWN_COMPONENT_IDS, (
            f"{view} has unknown ids: {set(ids) - KNOWN_COMPONENT_IDS}"
        )


def test_view_for_returns_set_with_locked_always_included():
    for tier in ("WA", "QA", "AA", "GA", "ZA"):
        v = view_for(tier)
        assert isinstance(v, set)
        assert STRUCTURAL_LOCKED <= v, f"{tier} missing locked components"


def test_view_for_wa_uses_minimal_actionable_default():
    v = view_for("WA")
    assert "per_question_eval" not in v
    assert "dam_matrix" in v
    assert "qrd_table" in v


def test_view_for_qa_uses_full_default():
    v = view_for("QA")
    assert "per_question_eval" in v
    assert "rubric_matrix" in v


def test_view_for_unknown_tier_falls_back():
    v = view_for("XX")
    assert STRUCTURAL_LOCKED <= v


def test_defaults_for_returns_list_for_each_tier():
    for tier in ("WA", "QA", "AA", "GA", "ZA"):
        d = defaults_for(tier)
        assert isinstance(d, list) and len(d) > 0
