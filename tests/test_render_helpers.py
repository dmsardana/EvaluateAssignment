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


def test_dam_matrix_derives_score_from_dimensions_when_missing():
    ev = {"questions": [{
        "difficulty": "D3",
        "learning_objective": "L4",
        "dimensions": {
            "concept_understanding": {"score": 0.8},
            "approach_method":       {"score": 0.6},
            "step_by_step":          {"score": 1.0},
            "numerical_accuracy":    {"score": 1.0},
            "presentation":          {"score": 0.6},
        },
    }]}
    g = make_dam_matrix(ev)
    assert g[2][3]["count"] == 1
    assert abs(g[2][3]["avg_pct"] - 80.0) < 0.01


def test_dam_matrix_defaults_d2_l2_for_missing_classification():
    ev = {"questions": [{"score": 0.5}]}
    g = make_dam_matrix(ev)
    assert g[1][1]["count"] == 1
    assert g[1][1]["avg_pct"] == 50.0


def test_qrd_rows_apply_defaults_for_legacy_questions():
    ev = {"questions": [{"number": 1, "topic": "Quadratics"}]}
    rows = make_qrd_rows(ev)
    assert rows[0]["difficulty"] == "D2"
    assert rows[0]["learning_objective"] == "L2"
    assert rows[0]["concept"] == "Quadratics"
    assert rows[0]["attempted"] is True


def test_qrd_rows_marks_blank_as_not_attempted():
    ev = {"questions": [
        {"number": 1, "your_answer": "(blank)"},
        {"number": 2, "your_answer": "x=3"},
        {"number": 3, "attempted": False, "your_answer": "x=5"},
    ]}
    rows = make_qrd_rows(ev)
    assert rows[0]["attempted"] is False
    assert rows[1]["attempted"] is True
    assert rows[2]["attempted"] is False


def test_qrd_rows_includes_scan_quality_with_legacy_default():
    ev = {"questions": [
        {"number": 1, "scan_quality": "Poor"},
        {"number": 2},
    ]}
    rows = make_qrd_rows(ev)
    assert rows[0]["scan_quality"] == "Poor"
    assert rows[1]["scan_quality"] == "Good"
