"""Gemini API credential handle.

Validated via the public REST endpoint:
    GET https://generativelanguage.googleapis.com/v1beta/models?key=<API_KEY>

We deliberately avoid importing `google-genai` so the credential
registry stays lightweight and Phase 1 doesn't pull in a heavy SDK
before the actual vision-eval routing lands in Phase 2. urllib (stdlib)
is enough for a health probe.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from web.api.services.credentials import (
    CredentialBroken,
    RecoveryAction,
    Status,
)

log = logging.getLogger(__name__)

CACHE_TTL = timedelta(minutes=5)
PROBE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
PROBE_TIMEOUT_SEC = 5.0


class GeminiCredentialHandle:
    name: str = "gemini_api"

    def __init__(self) -> None:
        self._cached: tuple[Status, str | None, datetime] | None = None

    def check_health(self) -> tuple[Status, str | None]:
        if self._cached is not None:
            status, err, when = self._cached
            if datetime.now(timezone.utc) - when < CACHE_TTL:
                return status, err

        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            return self._cache(Status.MISSING, "GEMINI_API_KEY not set")

        req = urllib.request.Request(f"{PROBE_URL}?key={key}")
        try:
            with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT_SEC) as resp:
                if resp.status == 200:
                    return self._cache(Status.OK, None)
                return self._cache(Status.UNKNOWN, f"HTTP {resp.status}")
        except urllib.error.HTTPError as exc:
            # 400 / 401 / 403 → invalid or revoked key; 429 → key is fine
            # but rate-limited; other codes → unknown.
            body = ""
            try:
                body = exc.read().decode("utf-8", "replace")[:300]
            except Exception:  # noqa: BLE001
                pass
            if exc.code in (400, 401, 403):
                return self._cache(Status.REVOKED, body or f"HTTP {exc.code}")
            if exc.code == 429:
                return self._cache(Status.OK, None)
            return self._cache(Status.UNKNOWN, f"HTTP {exc.code} {body}")
        except urllib.error.URLError as exc:
            return self._cache(Status.UNKNOWN, str(exc.reason)[:200])
        except Exception as exc:  # noqa: BLE001
            return self._cache(Status.UNKNOWN, str(exc)[:200])

    def _cache(self, status: Status, err: str | None) -> tuple[Status, str | None]:
        self._cached = (status, err, datetime.now(timezone.utc))
        return status, err

    def get_recovery(self) -> RecoveryAction:
        return RecoveryAction(
            kind="text_field",
            start_url="/api/credentials/gemini_api/update",
            field="GEMINI_API_KEY",
        )

    def get_client(self):
        # Phase 2 returns a google.generativeai client here. For now the
        # registry only needs to surface status; live evaluation calls
        # still route to Anthropic.
        status, err = self.check_health()
        if status is not Status.OK:
            raise CredentialBroken(self.name, status, err)
        return {"api_key": os.environ["GEMINI_API_KEY"]}
