"""Edge-triggered ops email notifier with 4h rate limit and no-recursion guard."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Callable

from web.api.services.credentials import Status

log = logging.getLogger(__name__)

RATE_LIMIT = timedelta(hours=4)


class StatusEdgeNotifier:
    def __init__(
        self,
        send_email: Callable[..., None],
        read_one: Callable[[str], dict | None],
        update_notified_at: Callable[[str, datetime], None],
        recipient: str | None,
    ) -> None:
        self._send_email = send_email
        self._read_one = read_one
        self._update_notified_at = update_notified_at
        self._recipient = recipient

    def on_transition(self, name: str, old: Status, new: Status, err: str | None) -> None:
        if not self._recipient or old == new:
            return

        now = datetime.now(timezone.utc)
        try:
            row = self._read_one(name) or {}
        except Exception as exc:
            log.warning("notifier: cannot read state (%s); skipping email", exc)
            return

        prev = row.get("notified_at")
        if prev is not None and now - _ensure_utc(prev) < RATE_LIMIT:
            log.info("notifier: rate-limited %s (last %s)", name, prev)
            return

        recovered = new is Status.OK
        subject = (
            f"[evalassign] {name} RECOVERED"
            if recovered
            else f"[evalassign] {name} {new.value}"
        )
        body = (
            f"Credential: {name}\n"
            f"State: {old.value} -> {new.value}\n"
            f"Detail: {err or '-'}\n"
            f"Time: {now.isoformat()}\n\n"
            f"Manage at: /settings/credentials\n"
        )

        try:
            self._send_email(to=self._recipient, subject=subject, body=body)
        except Exception as exc:
            log.exception("notifier: send_email failed (%s)", exc)
            return

        try:
            self._update_notified_at(name, now)
        except Exception as exc:
            log.warning("notifier: could not record notified_at (%s)", exc)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
