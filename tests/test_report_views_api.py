import os

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="requires Postgres",
)


@pytest.fixture
def client():
    from web.api.main import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def _restore_wa(client):
    """Reset WA defaults before and after each test so we don't leave
    test selections in the live table."""
    client.post("/api/settings/report-views/reset", json={"tier": "WA"})
    yield
    client.post("/api/settings/report-views/reset", json={"tier": "WA"})


def test_get_report_views_returns_catalog_and_defaults(client):
    r = client.get("/api/settings/report-views")
    assert r.status_code == 200
    body = r.json()
    assert set(body["tiers"]) == {"WA", "QA", "AA", "GA", "ZA"}
    ids = {c["id"] for c in body["catalog"]}
    assert {"page1_header", "dam_matrix", "qrd_table", "per_question_eval"} <= ids
    assert "page1_header" in body["by_tier"]["WA"]
    assert "per_question_eval" in body["defaults"]["QA"]


def test_put_report_views_persists_and_forces_locked(client):
    body = {"by_tier": {"WA": ["score_block", "improvements"]}}
    r = client.put("/api/settings/report-views", json=body)
    assert r.status_code == 200
    saved = client.get("/api/settings/report-views").json()
    locked = {"page1_header", "student_block", "score_block", "page_footer"}
    assert locked <= set(saved["by_tier"]["WA"])
    assert "improvements" in saved["by_tier"]["WA"]


def test_put_rejects_unknown_component_id(client):
    body = {"by_tier": {"WA": ["not_a_real_component"]}}
    r = client.put("/api/settings/report-views", json=body)
    assert r.status_code == 422


def test_put_rejects_unknown_tier(client):
    body = {"by_tier": {"XX": ["score_block"]}}
    r = client.put("/api/settings/report-views", json=body)
    assert r.status_code == 422


def test_reset_restores_defaults(client):
    client.put(
        "/api/settings/report-views",
        json={"by_tier": {"WA": ["score_block"]}},
    )
    r = client.post("/api/settings/report-views/reset", json={"tier": "WA"})
    assert r.status_code == 200
    saved = client.get("/api/settings/report-views").json()
    assert "summary_box" in saved["by_tier"]["WA"]
