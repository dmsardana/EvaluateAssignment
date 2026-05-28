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


# ---- OAuth flow helpers
from datetime import datetime, timezone, timedelta

from google_auth_oauthlib.flow import Flow

_PENDING_FLOWS: dict[str, Flow] = {}
_LAST_FLOW_STATE: dict[str, tuple[str, datetime]] = {}

# OAuth callback URL. Must match a registered redirect URI in
# Google Cloud Console (APIs & Services → Credentials → OAuth 2.0
# Client → Authorized redirect URIs). Override via API_PORT env if
# uvicorn runs on a port other than the default 8001.
_API_PORT = os.environ.get("API_PORT", "8001").strip() or "8001"
CALLBACK_URL = f"http://localhost:{_API_PORT}/api/credentials/google_oauth/oauth-callback"


def start_reauth_flow() -> tuple[str, str]:
    """Returns (consent_url, state). Idempotent within a 5-minute window."""
    now = datetime.now(timezone.utc)
    prev = _LAST_FLOW_STATE.get("google_oauth")
    if prev is not None:
        state, started = prev
        if now - started < timedelta(minutes=5) and state in _PENDING_FLOWS:
            flow = _PENDING_FLOWS[state]
            consent_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
            return consent_url, state

    creds_path = str(Path(__file__).resolve().parents[4] / "credentials.json")
    flow = Flow.from_client_secrets_file(
        creds_path,
        scopes=list(DEFAULT_SCOPES),
        redirect_uri=CALLBACK_URL,
    )
    consent_url, state = flow.authorization_url(prompt="consent", access_type="offline")
    _PENDING_FLOWS[state] = flow
    _LAST_FLOW_STATE["google_oauth"] = (state, now)
    return consent_url, state


def finish_reauth_flow(code: str, state: str, token_path: Path) -> None:
    """Complete the OAuth flow:
       1. Look up the pending Flow by state token
       2. Exchange code for tokens
       3. Validate with a Drive API probe
       4. Atomically write token.json
       5. Report OK to REGISTRY
    """
    from web.api.services.credentials import REGISTRY

    flow = _PENDING_FLOWS.pop(state, None)
    if flow is None:
        raise ValueError("invalid or expired state token")

    flow.fetch_token(code=code)
    creds = flow.credentials
    if not _validate_creds_with_drive_call(creds):
        raise ValueError("new token did not pass Drive validation probe")

    token_path = Path(token_path)
    tmp = token_path.with_suffix(token_path.suffix + ".tmp")
    tmp.write_text(creds.to_json())
    os.replace(tmp, token_path)

    REGISTRY.report_status("google_oauth", Status.OK, None)


def _validate_creds_with_drive_call(creds) -> bool:
    try:
        drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        drive.about().get(fields="user").execute()
        return True
    except Exception as exc:
        log.warning("token validation failed: %s", exc)
        return False
