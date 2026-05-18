from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _make_handle(name: str) -> MagicMock:
    h = MagicMock()
    h.name = name
    h.check_health.return_value = ("OK", None)
    return h


def test_register_and_get():
    from web.api.services.credentials import Registry

    reg = Registry()
    h = _make_handle("google_oauth")
    reg.register(h)
    assert reg.get("google_oauth") is h


def test_get_unknown_raises_keyerror():
    from web.api.services.credentials import Registry

    reg = Registry()
    with pytest.raises(KeyError):
        reg.get("nope")


def test_all_returns_registered_handles_in_order():
    from web.api.services.credentials import Registry

    reg = Registry()
    a, b = _make_handle("a"), _make_handle("b")
    reg.register(a)
    reg.register(b)
    assert reg.all() == [a, b]


def test_report_status_stores_in_memory_when_no_store():
    from web.api.services.credentials import Registry, Status

    reg = Registry()
    reg.report_status("google_oauth", Status.REVOKED, "invalid_grant")
    snap = reg.snapshot()
    assert snap["google_oauth"].status == Status.REVOKED
    assert snap["google_oauth"].last_error == "invalid_grant"


def test_module_level_singleton_exists():
    from web.api.services import credentials

    assert hasattr(credentials, "REGISTRY")
    assert isinstance(credentials.REGISTRY, credentials.Registry)
