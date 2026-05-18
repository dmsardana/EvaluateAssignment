"""Shared fixtures for web.api credential-registry tests."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def tmp_token_file(tmp_path: Path) -> Path:
    """A temporary token.json path that tests can write to without touching the real one."""
    return tmp_path / "token.json"


@pytest.fixture
def fake_anthropic_client() -> MagicMock:
    """A MagicMock that stands in for anthropic.Anthropic()."""
    client = MagicMock()
    client.models.list.return_value = MagicMock(data=[MagicMock(id="claude-opus-4-7")])
    return client


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wipe env vars the credentials module reads, so tests start clean."""
    for k in ("ANTHROPIC_API_KEY", "OPS_ALERT_EMAIL", "GOOGLE_TOKEN_PATH"):
        monkeypatch.delenv(k, raising=False)
