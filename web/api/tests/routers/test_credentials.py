from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from web.api.services.credentials import Status


@pytest.fixture
def client():
    from web.api.main import app
    return TestClient(app)


def test_status_endpoint_returns_list(client, monkeypatch):
    fake_rows = [
        {"name": "google_oauth", "status": "OK",
         "last_checked_at": datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
         "last_ok_at": datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
         "last_error": None, "recovery_started_at": None,
         "notified_at": None,
         "updated_at": datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)},
    ]
    monkeypatch.setattr("web.api.routers.credentials.store.read_all",
                        lambda: fake_rows)
    monkeypatch.setattr("web.api.routers.credentials._auth_required",
                        lambda req: None)

    resp = client.get("/api/credentials/status")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert body[0]["name"] == "google_oauth"
    assert body[0]["status"] == "OK"


def test_recheck_triggers_check_health(client, monkeypatch):
    handle = MagicMock(name="handle")
    handle.check_health.return_value = (Status.OK, None)
    monkeypatch.setattr("web.api.routers.credentials._auth_required",
                        lambda req: None)
    monkeypatch.setattr("web.api.routers.credentials.REGISTRY.get",
                        lambda name: handle)

    resp = client.post("/api/credentials/google_oauth/recheck")
    assert resp.status_code == 200
    handle.check_health.assert_called_once()


def test_recheck_unknown_returns_404(client, monkeypatch):
    monkeypatch.setattr("web.api.routers.credentials._auth_required",
                        lambda req: None)
    monkeypatch.setattr("web.api.routers.credentials.REGISTRY.get",
                        MagicMock(side_effect=KeyError("nope")))
    resp = client.post("/api/credentials/nope/recheck")
    assert resp.status_code == 404


def test_reauth_returns_consent_url(client, monkeypatch):
    monkeypatch.setattr("web.api.routers.credentials._auth_required",
                        lambda req: None)
    monkeypatch.setattr(
        "web.api.routers.credentials.google_module.start_reauth_flow",
        lambda: ("https://accounts.google.com/o/oauth2/auth?fake=1", "STATE-TOKEN"),
    )
    resp = client.post("/api/credentials/google_oauth/reauth")
    assert resp.status_code == 200
    body = resp.json()
    assert body["consent_url"].startswith("https://accounts.google.com/")
    assert body["state"] == "STATE-TOKEN"


def test_reauth_idempotent_within_window(client, monkeypatch):
    monkeypatch.setattr("web.api.routers.credentials._auth_required",
                        lambda req: None)
    calls = []
    def fake_start():
        calls.append(1)
        return ("https://x/", "S")
    monkeypatch.setattr(
        "web.api.routers.credentials.google_module.start_reauth_flow",
        fake_start,
    )
    r1 = client.post("/api/credentials/google_oauth/reauth")
    r2 = client.post("/api/credentials/google_oauth/reauth")
    assert r1.json()["state"] == r2.json()["state"]
