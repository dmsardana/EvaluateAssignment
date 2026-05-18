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
        now = datetime.now(timezone.utc)
        snap = self._snaps.setdefault(name, HealthSnapshot(name=name))
        snap.status = status
        snap.last_checked_at = now
        snap.last_error = err
        if status is Status.OK:
            snap.last_ok_at = now


REGISTRY = Registry()
