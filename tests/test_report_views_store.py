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
    execute("DELETE FROM report_view_settings WHERE tier LIKE %s", ("TST_%",))
    store.invalidate_cache()
    yield
    execute("DELETE FROM report_view_settings WHERE tier LIKE %s", ("TST_%",))
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


def test_reset_returns_defaults_for_tier():
    store.save("TST_WA", ["page1_header"])
    defaults = store.reset("TST_WA")
    assert store.load("TST_WA") is None
    assert isinstance(defaults, list) and len(defaults) > 0


def test_view_for_consults_store_when_override_present():
    from tools.report_view_config import view_for
    store.save("TST_WA", ["page1_header", "summary_box"])
    v = view_for("TST_WA")
    assert "summary_box" in v
    assert "per_question_eval" not in v
