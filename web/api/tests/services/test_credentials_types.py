from __future__ import annotations


def test_status_enum_values():
    from web.api.services.credentials import Status
    assert {s.value for s in Status} == {"OK", "EXPIRED", "REVOKED", "MISSING", "UNKNOWN"}


def test_credential_broken_carries_name_and_status():
    from web.api.services.credentials import CredentialBroken, Status

    err = CredentialBroken(name="google_oauth", status=Status.REVOKED, reason="invalid_grant")
    assert err.name == "google_oauth"
    assert err.status == Status.REVOKED
    assert err.reason == "invalid_grant"
    assert "google_oauth" in str(err)
    assert "REVOKED" in str(err)


def test_recovery_action_has_kind_and_start_url():
    from web.api.services.credentials import RecoveryAction

    ra = RecoveryAction(kind="oauth", start_url="/api/credentials/google_oauth/reauth")
    assert ra.kind == "oauth"
    assert ra.start_url == "/api/credentials/google_oauth/reauth"
