from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time

from web.api.services.credentials import Status


def _make_notifier(send_email_mock, store_mock):
    from web.api.services.credentials.notifier import StatusEdgeNotifier
    return StatusEdgeNotifier(
        send_email=send_email_mock,
        read_one=store_mock["read_one"],
        update_notified_at=store_mock["update_notified_at"],
        recipient="ops@example.com",
    )


@pytest.fixture
def store_mock():
    return {
        "read_one": MagicMock(return_value={"notified_at": None}),
        "update_notified_at": MagicMock(),
    }


def test_emails_on_ok_to_revoked_transition(store_mock):
    send = MagicMock()
    n = _make_notifier(send, store_mock)
    n.on_transition("google_oauth", Status.OK, Status.REVOKED, "invalid_grant")
    assert send.call_count == 1


def test_emails_on_revoked_to_ok_transition(store_mock):
    send = MagicMock()
    n = _make_notifier(send, store_mock)
    n.on_transition("google_oauth", Status.REVOKED, Status.OK, None)
    assert send.call_count == 1
    subject = send.call_args.kwargs.get("subject") or send.call_args.args[0]
    assert "RECOVERED" in subject


def test_no_email_when_status_unchanged(store_mock):
    send = MagicMock()
    n = _make_notifier(send, store_mock)
    n.on_transition("google_oauth", Status.REVOKED, Status.REVOKED, "invalid_grant")
    send.assert_not_called()


def test_rate_limit_4h(store_mock):
    send = MagicMock()
    n = _make_notifier(send, store_mock)
    with freeze_time("2026-05-18 12:00:00") as frozen:
        n.on_transition("google_oauth", Status.OK, Status.REVOKED, "x")
        assert send.call_count == 1

        store_mock["read_one"].return_value = {"notified_at": datetime.now(timezone.utc)}
        frozen.tick(timedelta(hours=1))
        n.on_transition("google_oauth", Status.OK, Status.REVOKED, "x")
        assert send.call_count == 1  # rate-limited

        frozen.tick(timedelta(hours=3, minutes=2))
        n.on_transition("google_oauth", Status.OK, Status.REVOKED, "x")
        assert send.call_count == 2


def test_no_recursion_when_send_email_fails(store_mock, caplog):
    send = MagicMock(side_effect=RuntimeError("gmail down"))
    n = _make_notifier(send, store_mock)
    n.on_transition("google_oauth", Status.OK, Status.REVOKED, "x")  # must not raise
    assert any("gmail down" in r.message.lower() for r in caplog.records)
