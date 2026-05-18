from __future__ import annotations

from unittest.mock import MagicMock

from web.api.services.credentials import Status


def test_run_one_tick_checks_every_handle(monkeypatch):
    from web.api.services.credentials.scheduler import run_one_tick

    h1 = MagicMock(name="h1"); h1.name = "a"; h1.check_health.return_value = (Status.OK, None)
    h2 = MagicMock(name="h2"); h2.name = "b"; h2.check_health.return_value = (Status.REVOKED, "x")

    fake_registry = MagicMock()
    fake_registry.all.return_value = [h1, h2]

    monkeypatch.setattr("web.api.services.credentials.scheduler.REGISTRY", fake_registry)
    run_one_tick()

    h1.check_health.assert_called_once()
    h2.check_health.assert_called_once()
    fake_registry.report_status.assert_any_call("a", Status.OK, None)
    fake_registry.report_status.assert_any_call("b", Status.REVOKED, "x")
