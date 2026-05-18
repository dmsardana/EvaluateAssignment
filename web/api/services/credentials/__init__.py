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
