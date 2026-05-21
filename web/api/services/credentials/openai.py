"""OpenAI API credential handle.

Validated via the public REST endpoint:
    GET https://api.openai.com/v1/models   (with `Authorization: Bearer …`)

Same rationale as gemini.py: stdlib urllib instead of pulling the
`openai` SDK in Phase 1. The actual vision-eval routing lands in
Phase 2 and can swap to the real SDK then.
"""
from __future__ import annotations

import logging
import os
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

# See gemini.py — same macOS Python.org SSL caveat applies.
try:
    import certifi
    _SSL_CONTEXT: ssl.SSLContext | None = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover
    _SSL_CONTEXT = None

from web.api.services.credentials import (
    CredentialBroken,
    RecoveryAction,
    Status,
)

log = logging.getLogger(__name__)

CACHE_TTL = timedelta(minutes=5)
PROBE_URL = "https://api.openai.com/v1/models"
PROBE_TIMEOUT_SEC = 5.0


class OpenAICredentialHandle:
    name: str = "openai_api"

    def __init__(self) -> None:
        self._cached: tuple[Status, str | None, datetime] | None = None

    def check_health(self) -> tuple[Status, str | None]:
        if self._cached is not None:
            status, err, when = self._cached
            if datetime.now(timezone.utc) - when < CACHE_TTL:
                return status, err

        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            return self._cache(Status.MISSING, "OPENAI_API_KEY not set")

        req = urllib.request.Request(
            PROBE_URL, headers={"Authorization": f"Bearer {key}"}
        )
        try:
            with urllib.request.urlopen(
                req, timeout=PROBE_TIMEOUT_SEC, context=_SSL_CONTEXT
            ) as resp:
                if resp.status == 200:
                    return self._cache(Status.OK, None)
                return self._cache(Status.UNKNOWN, f"HTTP {resp.status}")
        except urllib.error.HTTPError as exc:
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
            start_url="/api/credentials/openai_api/update",
            field="OPENAI_API_KEY",
        )

    def get_client(self):
        # Phase 2 returns an openai.OpenAI(api_key=…) client.
        status, err = self.check_health()
        if status is not Status.OK:
            raise CredentialBroken(self.name, status, err)
        return {"api_key": os.environ["OPENAI_API_KEY"]}
