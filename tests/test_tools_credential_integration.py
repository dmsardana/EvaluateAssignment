"""End-to-end test that pipeline tools degrade gracefully when creds are broken."""
from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from web.api.services.credentials import CredentialBroken, Status


def test_run_pipeline_tick_skips_when_google_revoked(caplog: pytest.LogCaptureFixture):
    """One tick of the pipeline against a REVOKED Google credential should:
       - not raise
       - log CREDENTIAL_BROKEN with credential name and status
       - return without doing any classroom work.
    """
    from tools import run_pipeline

    broken = CredentialBroken("google_oauth", Status.REVOKED, "invalid_grant")
    with (
        patch.object(run_pipeline, "_get_classroom", side_effect=broken),
        caplog.at_level(logging.ERROR),
    ):
        run_pipeline.tick()

    assert any(
        "CREDENTIAL_BROKEN" in r.message and "google_oauth" in r.message and "REVOKED" in r.message
        for r in caplog.records
    ), f"expected CREDENTIAL_BROKEN log line, got: {[r.message for r in caplog.records]}"
