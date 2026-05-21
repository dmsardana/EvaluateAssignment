"""
FastAPI dependency providers — Drive + Classroom service clients and the
folder/course IDs the rest of the API needs.

OAuth credentials live in ``token.json`` at the repo root, refreshed
in-place when expired. The credential registry (under
``web.api.services.credentials``) is the long-lived health-tracked
abstraction, but for raw Drive/Classroom build calls we read the token
file directly so this module stays simple and the registry's failure
modes don't cascade into ordinary route handlers.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Relax token-scope checking so a token issued with more scopes than we
# ask for still validates. Real scope enforcement happens server-side.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

# Path to the repo root — token.json lives there.
ROOT = Path(__file__).resolve().parents[2]

# Make tools/ importable for callers that import deps before the project
# is otherwise wired (e.g. uvicorn started from web/api/).
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from tools.setup_drive import SCOPES  # noqa: E402

_TOKEN_PATH = ROOT / "token.json"
_creds_cache: dict[str, object] = {}
_creds_lock = threading.Lock()


def _creds() -> Credentials:
    """Load Google OAuth credentials, refreshing if expired.

    Cached per-process keyed by ``token.json`` mtime so a token rotation
    is picked up on the next call without a server restart.
    """
    if not _TOKEN_PATH.exists():
        raise RuntimeError(
            f"token.json not found at {_TOKEN_PATH}. Run "
            "scripts/setup-oauth.py (or POST "
            "/api/credentials/google_oauth/reauth) to generate it."
        )
    mtime = _TOKEN_PATH.stat().st_mtime
    with _creds_lock:
        cached = _creds_cache.get("creds")
        cached_mtime = _creds_cache.get("mtime")
        if cached is None or cached_mtime != mtime:
            cached = Credentials.from_authorized_user_file(
                str(_TOKEN_PATH), SCOPES
            )
            _creds_cache["creds"] = cached
            _creds_cache["mtime"] = mtime
        creds = cached  # type: ignore[assignment]
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds  # type: ignore[return-value]


def get_drive():
    return build("drive", "v3", credentials=_creds(), cache_discovery=False)


def get_classroom():
    return build("classroom", "v1", credentials=_creds(), cache_discovery=False)


def get_classroom_factory():
    # googleapiclient's discovery client is not thread-safe, so per-thread
    # workers in ThreadPoolExecutor need their own instances. Routers pass
    # this factory into queue.list_queue / list_students_with_profiles /
    # score_matrix to enable their parallel fan-out branches.
    return get_classroom


def _first_env(*names: str) -> str:
    for n in names:
        v = (os.getenv(n) or "").strip()
        if v:
            return v
    return ""


def get_keys_folder_id() -> str:
    # Accept both the canonical name used by the original pipeline and the
    # short DRIVE_* names found in .env.
    fid = _first_env("GOOGLE_KEYS_FOLDER_ID", "DRIVE_KEYS_ID")
    if not fid:
        raise RuntimeError(
            "GOOGLE_KEYS_FOLDER_ID (or DRIVE_KEYS_ID) is not set in .env. "
            "Add the Drive folder id where answer keys are uploaded."
        )
    return fid


def get_reports_folder_id() -> str:
    fid = _first_env("GOOGLE_REPORTS_FOLDER_ID", "DRIVE_REPORTS_ID")
    if not fid:
        raise RuntimeError(
            "GOOGLE_REPORTS_FOLDER_ID (or DRIVE_REPORTS_ID) is not set in "
            ".env. Add the Drive folder id where graded reports are uploaded."
        )
    return fid


def get_course_ids() -> list[str]:
    raw = _first_env("GOOGLE_COURSE_IDS", "CLASSROOM_COURSE_IDS")
    if not raw:
        return []
    return [c.strip() for c in raw.split(",") if c.strip()]
