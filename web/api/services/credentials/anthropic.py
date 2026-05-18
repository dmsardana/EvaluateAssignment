"""Anthropic API credential handle. Validated via models.list()."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta

import anthropic

from web.api.services.credentials import (
    CredentialBroken,
    RecoveryAction,
    Status,
)

log = logging.getLogger(__name__)

CACHE_TTL = timedelta(minutes=5)


class AnthropicCredentialHandle:
    name: str = "anthropic_api"

    def __init__(self) -> None:
        self._cached: tuple[Status, str | None, datetime] | None = None

    def check_health(self) -> tuple[Status, str | None]:
        if self._cached is not None:
            status, err, when = self._cached
            if datetime.now(timezone.utc) - when < CACHE_TTL:
                return status, err

        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            return self._cache(Status.MISSING, "ANTHROPIC_API_KEY not set")

        try:
            client = self._make_client(key)
            client.models.list()
        except anthropic.AuthenticationError as exc:
            return self._cache(Status.REVOKED, str(exc)[:200])
        except anthropic.RateLimitError:
            return self._cache(Status.OK, None)
        except anthropic.APIError as exc:
            return self._cache(Status.UNKNOWN, str(exc)[:200])
        except Exception as exc:
            return self._cache(Status.UNKNOWN, str(exc)[:200])

        return self._cache(Status.OK, None)

    def _cache(self, status: Status, err: str | None) -> tuple[Status, str | None]:
        self._cached = (status, err, datetime.now(timezone.utc))
        return status, err

    def _make_client(self, key: str):
        return anthropic.Anthropic(api_key=key)

    def get_recovery(self) -> RecoveryAction:
        return RecoveryAction(
            kind="text_field",
            start_url="/api/credentials/anthropic_api/update",
            field="ANTHROPIC_API_KEY",
        )

    def get_client(self):
        status, err = self.check_health()
        if status is not Status.OK:
            raise CredentialBroken(self.name, status, err)
        return self._make_client(os.environ["ANTHROPIC_API_KEY"])
