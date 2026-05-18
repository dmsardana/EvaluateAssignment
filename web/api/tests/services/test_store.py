from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from web.api.services.credentials import Status

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — integration test against live Postgres",
)


def test_upsert_inserts_new_row():
    from web.api.services.credentials.store import upsert_health, read_all, delete_health

    name = "test_cred_a"
    now = datetime.now(timezone.utc)
    upsert_health(name=name, status=Status.OK, last_error=None, now=now)

    rows = {r["name"]: r for r in read_all()}
    assert name in rows
    assert rows[name]["status"] == "OK"
    assert rows[name]["last_ok_at"] is not None

    delete_health(name)


def test_upsert_updates_existing_row():
    from web.api.services.credentials.store import upsert_health, read_all, delete_health

    name = "test_cred_b"
    upsert_health(name=name, status=Status.OK, last_error=None,
                  now=datetime.now(timezone.utc))
    upsert_health(name=name, status=Status.REVOKED, last_error="invalid_grant",
                  now=datetime.now(timezone.utc))

    row = next(r for r in read_all() if r["name"] == name)
    assert row["status"] == "REVOKED"
    assert row["last_error"] == "invalid_grant"
    assert row["last_ok_at"] is not None  # preserved across the transition

    delete_health(name)
