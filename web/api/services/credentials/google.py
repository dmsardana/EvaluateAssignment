"""Google OAuth credential handle.

Owns token.json. Maps RefreshError variants into the Status enum.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from web.api.services.credentials import (
    CredentialBroken,
    RecoveryAction,
    Status,
)

os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

log = logging.getLogger(__name__)

DEFAULT_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students",
    "https://www.googleapis.com/auth/classroom.student-submissions.students.readonly",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
)


class GoogleCredentialHandle:
    name: str = "google_oauth"

    def __init__(self, token_path: Path | str, scopes: tuple[str, ...] = DEFAULT_SCOPES) -> None:
        self._token_path = Path(token_path)
        self._scopes = scopes

    def check_health(self) -> tuple[Status, str | None]:
        if not self._token_path.exists():
            return Status.MISSING, "token.json not found"

        try:
            creds = Credentials.from_authorized_user_file(str(self._token_path), list(self._scopes))
        except Exception as exc:
            return Status.UNKNOWN, f"could not parse token.json: {exc}"

        if creds.valid:
            return Status.OK, None

        if not creds.refresh_token:
            return Status.MISSING, "no refresh_token in token.json"

        try:
            creds.refresh(Request())
        except RefreshError as exc:
            msg = str(exc)
            if "invalid_grant" in msg:
                return Status.REVOKED, _scrub(msg)
            return Status.EXPIRED, _scrub(msg)
        except Exception as exc:
            return Status.UNKNOWN, _scrub(str(exc))

        self._atomic_write(creds)
        return Status.OK, None

    def get_recovery(self) -> RecoveryAction:
        return RecoveryAction(
            kind="oauth",
            start_url="/api/credentials/google_oauth/reauth",
        )

    def _atomic_write(self, creds: Credentials) -> None:
        tmp = self._token_path.with_suffix(self._token_path.suffix + ".tmp")
        tmp.write_text(creds.to_json())
        os.replace(tmp, self._token_path)

    def _ensure_ok(self) -> Credentials:
        status, err = self.check_health()
        if status is not Status.OK:
            raise CredentialBroken(self.name, status, err)
        return Credentials.from_authorized_user_file(str(self._token_path), list(self._scopes))

    def get_drive(self):
        creds = self._ensure_ok()
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    def get_classroom(self):
        creds = self._ensure_ok()
        return build("classroom", "v1", credentials=creds, cache_discovery=False)

    def get_gmail(self):
        creds = self._ensure_ok()
        return build("gmail", "v1", credentials=creds, cache_discovery=False)


_SECRET_NEEDLES = ("refresh_token", "access_token", "client_secret")


def _scrub(msg: str) -> str:
    out = msg[:200]
    for needle in _SECRET_NEEDLES:
        out = out.replace(needle, "[redacted]")
    return out
