from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from web.api.services.credentials import Status


def test_missing_api_key_returns_missing(monkeypatch):
    from web.api.services.credentials.anthropic import AnthropicCredentialHandle
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    h = AnthropicCredentialHandle()
    assert h.check_health()[0] is Status.MISSING


def test_valid_key_returns_ok(monkeypatch):
    from web.api.services.credentials.anthropic import AnthropicCredentialHandle
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    h = AnthropicCredentialHandle()

    fake_client = MagicMock()
    fake_client.models.list.return_value = MagicMock(data=[])
    h._make_client = lambda key: fake_client  # type: ignore[method-assign]

    status, err = h.check_health()
    assert status is Status.OK
    assert err is None


def test_401_returns_revoked(monkeypatch):
    from web.api.services.credentials.anthropic import AnthropicCredentialHandle
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-bad")
    h = AnthropicCredentialHandle()

    import anthropic
    fake_client = MagicMock()
    fake_client.models.list.side_effect = anthropic.AuthenticationError(
        "invalid x-api-key",
        response=MagicMock(status_code=401),
        body=None,
    )
    h._make_client = lambda key: fake_client  # type: ignore[method-assign]

    status, err = h.check_health()
    assert status is Status.REVOKED


def test_429_returns_ok(monkeypatch):
    from web.api.services.credentials.anthropic import AnthropicCredentialHandle
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    h = AnthropicCredentialHandle()

    import anthropic
    fake_client = MagicMock()
    fake_client.models.list.side_effect = anthropic.RateLimitError(
        "rate limited",
        response=MagicMock(status_code=429),
        body=None,
    )
    h._make_client = lambda key: fake_client  # type: ignore[method-assign]

    status, _ = h.check_health()
    assert status is Status.OK


def test_check_health_caches_for_5_min(monkeypatch):
    from web.api.services.credentials.anthropic import AnthropicCredentialHandle
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    h = AnthropicCredentialHandle()

    fake_client = MagicMock()
    fake_client.models.list.return_value = MagicMock(data=[])
    h._make_client = lambda key: fake_client  # type: ignore[method-assign]

    h.check_health()
    h.check_health()
    assert fake_client.models.list.call_count == 1
