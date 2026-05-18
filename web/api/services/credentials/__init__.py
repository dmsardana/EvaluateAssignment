"""Credential Registry — uniform abstraction for external API credentials.

Public surface:
    Status              — enum of credential lifecycle states
    CredentialBroken    — exception raised when a credential is not OK
    RecoveryAction      — value object describing how to recover (oauth | text_field)

Subsequent tasks add: CredentialHandle protocol, Registry singleton, default registration.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Status(str, Enum):
    OK = "OK"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RecoveryAction:
    kind: str           # "oauth" | "text_field"
    start_url: str      # where to POST to start the flow / submit the value
    field: str | None = None   # only for kind="text_field"


class CredentialBroken(Exception):
    """Raised by handle.get_client() when status is not OK."""

    def __init__(self, name: str, status: Status, reason: str | None = None) -> None:
        self.name = name
        self.status = status
        self.reason = reason
        super().__init__(f"{name} is {status.value}: {reason or 'no detail'}")


from datetime import datetime, timezone
from typing import Protocol


class CredentialHandle(Protocol):
    """The interface every credential implements."""
    name: str

    def check_health(self) -> tuple[Status, str | None]: ...
    def get_recovery(self) -> RecoveryAction: ...


@dataclass
class HealthSnapshot:
    """In-memory view of a credential's current health."""
    name: str
    status: Status = Status.UNKNOWN
    last_checked_at: datetime | None = None
    last_ok_at: datetime | None = None
    last_error: str | None = None


class Registry:
    """The Registry is the only place that knows the list of credentials."""

    def __init__(self) -> None:
        self._handles: dict[str, CredentialHandle] = {}
        self._snaps: dict[str, HealthSnapshot] = {}
        self._subscribers: list = []

    def register(self, handle: CredentialHandle) -> None:
        if handle.name in self._handles:
            raise ValueError(f"credential {handle.name!r} already registered")
        self._handles[handle.name] = handle
        self._snaps[handle.name] = HealthSnapshot(name=handle.name)

    def get(self, name: str) -> CredentialHandle:
        return self._handles[name]

    def all(self) -> list[CredentialHandle]:
        return list(self._handles.values())

    def snapshot(self) -> dict[str, HealthSnapshot]:
        return dict(self._snaps)

    def report_status(self, name: str, status: Status, err: str | None) -> None:
        import logging

        log = logging.getLogger(__name__)
        now = datetime.now(timezone.utc)

        # In-memory snapshot first — independent of DB success.
        snap = self._snaps.setdefault(name, HealthSnapshot(name=name))
        prev_status = snap.status
        snap.status = status
        snap.last_checked_at = now
        snap.last_error = err
        if status is Status.OK:
            snap.last_ok_at = now

        # Persist (best-effort).
        try:
            from web.api.services.credentials import store
            store.upsert_health(name=name, status=status, last_error=err, now=now)
        except Exception as exc:  # noqa: BLE001
            log.warning("credentials store unavailable, in-memory only: %s", exc)

        # Fire transition callbacks.
        if prev_status != status:
            self._fire_transition(name, prev_status, status, err)

    def subscribe_transition(self, fn) -> None:
        self._subscribers.append(fn)

    def _fire_transition(self, name: str, old: Status, new: Status, err: str | None) -> None:
        import logging
        for fn in self._subscribers:
            try:
                fn(name, old, new, err)
            except Exception:  # noqa: BLE001
                logging.getLogger(__name__).exception("notifier subscriber failed")


REGISTRY = Registry()

# Populate the singleton with the default handles.
from web.api.services.credentials.register_defaults import register_defaults  # noqa: E402

register_defaults()
