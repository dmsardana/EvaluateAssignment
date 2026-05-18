from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from google.auth.exceptions import RefreshError

from web.api.services.credentials import Status


@pytest.fixture
def valid_token_file(tmp_path: Path) -> Path:
    p = tmp_path / "token.json"
    p.write_text(json.dumps({
        "token": "ya29.fake",
        "refresh_token": "1//fake",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "fake.apps.googleusercontent.com",
        "client_secret": "fake-secret",
        "scopes": ["https://www.googleapis.com/auth/drive"],
    }))
    return p


def test_check_health_missing_token_returns_missing(tmp_path: Path):
    from web.api.services.credentials.google import GoogleCredentialHandle

    h = GoogleCredentialHandle(token_path=tmp_path / "does-not-exist.json")
    status, err = h.check_health()
    assert status is Status.MISSING
    assert "not found" in (err or "").lower()


def test_check_health_valid_creds_returns_ok(valid_token_file: Path):
    from web.api.services.credentials.google import GoogleCredentialHandle

    h = GoogleCredentialHandle(token_path=valid_token_file)
    fake_creds = MagicMock(valid=True, expired=False, refresh_token="1//fake")
    with patch("web.api.services.credentials.google.Credentials.from_authorized_user_file",
               return_value=fake_creds):
        status, err = h.check_health()
    assert status is Status.OK
    assert err is None


def test_check_health_invalid_grant_returns_revoked(valid_token_file: Path):
    from web.api.services.credentials.google import GoogleCredentialHandle

    h = GoogleCredentialHandle(token_path=valid_token_file)
    fake_creds = MagicMock(valid=False, expired=True, refresh_token="1//fake")
    fake_creds.refresh.side_effect = RefreshError(
        "invalid_grant: Token has been expired or revoked.",
        {"error": "invalid_grant"},
    )
    with patch("web.api.services.credentials.google.Credentials.from_authorized_user_file",
               return_value=fake_creds):
        status, err = h.check_health()
    assert status is Status.REVOKED
    assert "invalid_grant" in (err or "")


def test_check_health_generic_refresh_error_returns_expired(valid_token_file: Path):
    from web.api.services.credentials.google import GoogleCredentialHandle

    h = GoogleCredentialHandle(token_path=valid_token_file)
    fake_creds = MagicMock(valid=False, expired=True, refresh_token="1//fake")
    fake_creds.refresh.side_effect = RefreshError("network blip", {})
    with patch("web.api.services.credentials.google.Credentials.from_authorized_user_file",
               return_value=fake_creds):
        status, err = h.check_health()
    assert status is Status.EXPIRED


def test_atomic_write_does_not_corrupt_existing_token(valid_token_file: Path, monkeypatch: pytest.MonkeyPatch):
    """If os.replace fails after the temp file is written, the original is untouched."""
    from web.api.services.credentials.google import GoogleCredentialHandle

    h = GoogleCredentialHandle(token_path=valid_token_file)
    original = valid_token_file.read_text()

    fake_creds = MagicMock()
    fake_creds.to_json.return_value = '{"token": "new"}'

    def boom(src, dst):
        raise OSError("simulated disk full")

    monkeypatch.setattr("web.api.services.credentials.google.os.replace", boom)

    with pytest.raises(OSError):
        h._atomic_write(fake_creds)

    assert valid_token_file.read_text() == original
