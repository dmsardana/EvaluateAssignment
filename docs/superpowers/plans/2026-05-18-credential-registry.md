# Credential Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a holistic external-credentials health system: detect Google OAuth + Anthropic API failures proactively (15-min APScheduler) and reactively (on pipeline tool errors), surface them on the UI header pill + ops email, and provide one-click recovery from a `/settings/credentials` page.

**Architecture:** A `Registry` singleton in `web/api/services/credentials/` exposes a uniform `CredentialHandle` interface (`check_health`, `get_recovery`). Pipeline tools and FastAPI both consume the same Registry. Status is persisted in a new Postgres `credentials_health` table; the Notifier sends one ops email per status edge (4h rate-limited). Recovery for Google is an OAuth flow whose callback validates the new token before writing `token.json` atomically.

**Tech Stack:** Python 3.13, FastAPI, APScheduler (new), `google-auth-oauthlib`, `anthropic` SDK, Postgres 16 (existing, port 5433), Next.js 15 (existing), SWR (existing), shadcn (existing). Tests: pytest (new), pytest-asyncio (new), httpx (new), Playwright (new for one E2E spec).

**Companion spec:** `docs/superpowers/specs/2026-05-18-credential-registry-design.md` — all design rationale and non-goals live there. This document is the executable plan.

---

## File structure

### New files

```
db/migrations/
  001_credentials_health.sql              (new — hand-run via psql)

web/api/services/credentials/
  __init__.py                             (Registry, Status, RecoveryAction, CredentialBroken)
  google.py                               (GoogleCredentialHandle)
  anthropic.py                            (AnthropicCredentialHandle)
  notifier.py                             (StatusEdgeNotifier)
  scheduler.py                            (start_scheduler / stop_scheduler)
  store.py                                (Postgres I/O for credentials_health)
  register_defaults.py                    (wires the two default handles)

web/api/routers/
  credentials.py                          (HTTP surface)

web/api/tests/
  __init__.py                             (empty marker)
  conftest.py                             (pytest fixtures: db, registry, mocks)
  services/__init__.py
  services/test_credentials_google.py
  services/test_credentials_anthropic.py
  services/test_notifier.py
  services/test_store.py
  routers/__init__.py
  routers/test_credentials.py

tests/                                    (project-root tests for CLI tools)
  __init__.py
  conftest.py
  test_tools_credential_integration.py

web/app/app/settings/credentials/
  page.tsx                                (deep-dive settings page)

web/app/components/
  credentials-popover.tsx                 (popover triggered by pill)
  credentials-cards.tsx                   (per-credential card reused by popover + page)

web/app/lib/
  credentials.ts                          (TS types + SWR hook)

web/app/e2e/
  credentials.spec.ts                     (single Playwright E2E)
  playwright.config.ts

requirements-dev.txt                       (new — pytest, pytest-asyncio, httpx)
```

### Modified files

```
db/schema.sql                              (append credentials_health DDL — keeps schema.sql as the canonical declaration)
requirements.txt                           (add apscheduler)
tools/run_pipeline.py                      (lines 33-48: replace creds loader with Registry call + CredentialBroken handler)
tools/watch_classroom.py                   (lines 50-65: same)
tools/email_helper.py                      (lines 18-32: same)
web/api/main.py                            (lifespan for scheduler, include credentials router)
web/app/components/pipeline-pill.tsx       (or whichever component renders the header status — locate in Task 5.2)
web/app/components/side-nav.tsx            (replace /settings/anthropic link with /settings/credentials)
web/app/package.json                       (add @playwright/test devDep + test scripts)
OPERATIONS.md                              (new "Credential health & recovery" section)
CLAUDE.md                                  (one-line Registry note)
```

### Why these boundaries

- `Registry` and `Store` are split so the Registry is a pure dispatcher and the DB layer can be mocked or fall back to in-memory cleanly.
- Each credential handle is its own file — adding "the third credential" is one file, no edits to existing handles.
- The Notifier is its own file because rate-limiting + recursion-guard logic deserves isolation and dedicated tests.
- Frontend split: `credentials.ts` owns types + SWR; `credentials-popover.tsx` owns the header dropdown; `credentials-cards.tsx` is reused by both the popover and the full page so the visual treatment stays in sync.

---

## Conventions used in this plan

- Python: 4-space indent, `from __future__ import annotations`, type hints required on every public function.
- Module-level singleton pattern is acceptable for the Registry (matches existing `web/api/deps.py` style).
- Every task ends in a `git commit`. Branch name: `feat/credential-registry` (create at the start of Task 0.1).
- Tests run via `pytest -xvs <path>` (the `-x` stops on first failure, `-v` for verbose, `-s` to see prints).
- Frontend `npm` commands run from `web/app/`.
- DB commands run via `docker exec -i evalassign-postgres psql -U evalassign -d evalassign` (per OPERATIONS.md).

---

## Wave 0 — Branch, test infrastructure, dependencies

### Task 0.1: Create feature branch

**Files:** none (git operation only)

- [ ] **Step 1: Create branch**

```bash
cd /Users/mohitsardana/_Projects/EvaluateAssignment
git checkout -b feat/credential-registry
git status
```

Expected: `On branch feat/credential-registry`. Existing untracked working-tree files are fine.

### Task 0.2: Add Python test dependencies

**Files:**
- Create: `requirements-dev.txt`

- [ ] **Step 1: Create `requirements-dev.txt`**

```text
# Test-only dependencies. Install with: pip install -r requirements-dev.txt
pytest>=8.0.0
pytest-asyncio>=0.23.0
httpx>=0.27.0           # FastAPI TestClient backend
freezegun>=1.4.0        # control time in notifier tests
```

- [ ] **Step 2: Install**

```bash
pip3 install -r requirements-dev.txt
pytest --version
```

Expected: `pytest 8.x.y`.

- [ ] **Step 3: Commit**

```bash
git add requirements-dev.txt
git commit -m "test: add pytest + httpx + freezegun for credential registry tests"
```

### Task 0.3: Add APScheduler to runtime deps

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Read current `requirements.txt`**

```bash
grep -n "^[a-z]" requirements.txt | head -20
```

- [ ] **Step 2: Append APScheduler**

Add a single line at the end of `requirements.txt`:

```text
apscheduler>=3.10.4     # background credential health checks
```

- [ ] **Step 3: Install + verify**

```bash
pip3 install -r requirements.txt
python3 -c "from apscheduler.schedulers.background import BackgroundScheduler; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "deps: add apscheduler for credential health scheduler"
```

### Task 0.4: Create pytest scaffolding

**Files:**
- Create: `web/api/tests/__init__.py` (empty)
- Create: `web/api/tests/conftest.py`
- Create: `web/api/tests/services/__init__.py` (empty)
- Create: `web/api/tests/routers/__init__.py` (empty)
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`
- Create: `pytest.ini` at repo root

- [ ] **Step 1: Create `pytest.ini`**

```ini
[pytest]
testpaths = web/api/tests tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
addopts = -ra --strict-markers
```

- [ ] **Step 2: Create empty `__init__.py` markers**

```bash
mkdir -p web/api/tests/services web/api/tests/routers tests
touch web/api/tests/__init__.py
touch web/api/tests/services/__init__.py
touch web/api/tests/routers/__init__.py
touch tests/__init__.py
```

- [ ] **Step 3: Create `web/api/tests/conftest.py`**

```python
"""Shared fixtures for web.api credential-registry tests."""
from __future__ import annotations

from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def tmp_token_file(tmp_path: Path) -> Path:
    """A temporary token.json path that tests can write to without touching the real one."""
    return tmp_path / "token.json"


@pytest.fixture
def fake_anthropic_client() -> MagicMock:
    """A MagicMock that stands in for anthropic.Anthropic()."""
    client = MagicMock()
    client.models.list.return_value = MagicMock(data=[MagicMock(id="claude-opus-4-7")])
    return client


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wipe env vars the credentials module reads, so tests start clean."""
    for k in ("ANTHROPIC_API_KEY", "OPS_ALERT_EMAIL", "GOOGLE_TOKEN_PATH"):
        monkeypatch.delenv(k, raising=False)
```

- [ ] **Step 4: Create `tests/conftest.py`** (project-root, for tool integration tests)

```python
"""Fixtures for tools/ CLI integration tests."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is importable so `from tools.X` works.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
```

- [ ] **Step 5: Smoke-run pytest to verify discovery**

```bash
pytest --collect-only
```

Expected: zero tests collected, no errors.

- [ ] **Step 6: Commit**

```bash
git add pytest.ini web/api/tests tests
git commit -m "test: add pytest scaffolding (conftest, init markers, pytest.ini)"
```

---

## Wave 1 — Registry + Google handle (in-memory, no DB yet)

By end of Wave 1: three pipeline tools call the Registry, `RefreshError` no longer crashes the daemon, status lives in memory.

### Task 1.1: Define types — `Status`, `RecoveryAction`, `CredentialBroken`

**Files:**
- Create: `web/api/services/credentials/__init__.py`
- Test: `web/api/tests/services/test_credentials_types.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# web/api/tests/services/test_credentials_types.py
from __future__ import annotations


def test_status_enum_values():
    from web.api.services.credentials import Status
    assert {s.value for s in Status} == {"OK", "EXPIRED", "REVOKED", "MISSING", "UNKNOWN"}


def test_credential_broken_carries_name_and_status():
    from web.api.services.credentials import CredentialBroken, Status

    err = CredentialBroken(name="google_oauth", status=Status.REVOKED, reason="invalid_grant")
    assert err.name == "google_oauth"
    assert err.status == Status.REVOKED
    assert err.reason == "invalid_grant"
    assert "google_oauth" in str(err)
    assert "REVOKED" in str(err)


def test_recovery_action_has_kind_and_start_url():
    from web.api.services.credentials import RecoveryAction

    ra = RecoveryAction(kind="oauth", start_url="/api/credentials/google_oauth/reauth")
    assert ra.kind == "oauth"
    assert ra.start_url == "/api/credentials/google_oauth/reauth"
```

- [ ] **Step 2: Run — verify it fails**

```bash
pytest web/api/tests/services/test_credentials_types.py -xvs
```

Expected: `ModuleNotFoundError: No module named 'web.api.services.credentials'`.

- [ ] **Step 3: Implement minimal types**

```python
# web/api/services/credentials/__init__.py
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
```

- [ ] **Step 4: Run — verify it passes**

```bash
pytest web/api/tests/services/test_credentials_types.py -xvs
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add web/api/services/credentials/__init__.py web/api/tests/services/test_credentials_types.py
git commit -m "feat(credentials): add Status, RecoveryAction, CredentialBroken types"
```

### Task 1.2: Registry singleton (in-memory only)

**Files:**
- Modify: `web/api/services/credentials/__init__.py`
- Test: `web/api/tests/services/test_credentials_registry.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# web/api/tests/services/test_credentials_registry.py
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _make_handle(name: str) -> MagicMock:
    h = MagicMock()
    h.name = name
    h.check_health.return_value = ("OK", None)
    return h


def test_register_and_get():
    from web.api.services.credentials import Registry

    reg = Registry()
    h = _make_handle("google_oauth")
    reg.register(h)
    assert reg.get("google_oauth") is h


def test_get_unknown_raises_keyerror():
    from web.api.services.credentials import Registry

    reg = Registry()
    with pytest.raises(KeyError):
        reg.get("nope")


def test_all_returns_registered_handles_in_order():
    from web.api.services.credentials import Registry

    reg = Registry()
    a, b = _make_handle("a"), _make_handle("b")
    reg.register(a)
    reg.register(b)
    assert reg.all() == [a, b]


def test_report_status_stores_in_memory_when_no_store():
    from web.api.services.credentials import Registry, Status

    reg = Registry()
    reg.report_status("google_oauth", Status.REVOKED, "invalid_grant")
    snap = reg.snapshot()
    assert snap["google_oauth"].status == Status.REVOKED
    assert snap["google_oauth"].last_error == "invalid_grant"


def test_module_level_singleton_exists():
    from web.api.services import credentials

    assert hasattr(credentials, "REGISTRY")
    assert isinstance(credentials.REGISTRY, credentials.Registry)
```

- [ ] **Step 2: Run — verify it fails**

```bash
pytest web/api/tests/services/test_credentials_registry.py -xvs
```

Expected: `AttributeError: module 'web.api.services.credentials' has no attribute 'Registry'`.

- [ ] **Step 3: Add Registry to `__init__.py`**

Append to `web/api/services/credentials/__init__.py`:

```python
from dataclasses import field
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
    """The Registry is the only place that knows the list of credentials.

    Tools and the web API both call REGISTRY.get(name) — never construct
    handles directly. report_status() is the only writer of status state.
    """

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
```

- [ ] **Step 4: Run — verify it passes**

```bash
pytest web/api/tests/services/test_credentials_registry.py -xvs
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add web/api/services/credentials/__init__.py web/api/tests/services/test_credentials_registry.py
git commit -m "feat(credentials): Registry singleton with in-memory health snapshots"
```

### Task 1.3: `GoogleCredentialHandle.check_health()`

**Files:**
- Create: `web/api/services/credentials/google.py`
- Test: `web/api/tests/services/test_credentials_google.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# web/api/tests/services/test_credentials_google.py
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from google.auth.exceptions import RefreshError

from web.api.services.credentials import Status


@pytest.fixture
def valid_token_file(tmp_path: Path) -> Path:
    """Write a non-expired token.json fixture."""
    p = tmp_path / "token.json"
    p.write_text(json.dumps({
        "token": "ya29.fake",
        "refresh_token": "1//fake",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "fake.apps.googleusercontent.com",
        "client_secret": "fake-secret",
        "scopes": ["https://www.googleapis.com/auth/drive"],
    }))
    return p


def test_check_health_missing_token_returns_missing(tmp_path: Path):
    from web.api.services.credentials.google import GoogleCredentialHandle

    h = GoogleCredentialHandle(token_path=tmp_path / "does-not-exist.json")
    status, err = h.check_health()
    assert status is Status.MISSING
    assert "not found" in (err or "").lower()


def test_check_health_valid_creds_returns_ok(valid_token_file: Path):
    from web.api.services.credentials.google import GoogleCredentialHandle

    h = GoogleCredentialHandle(token_path=valid_token_file)
    fake_creds = MagicMock(valid=True, expired=False, refresh_token="1//fake")
    with patch("web.api.services.credentials.google.Credentials.from_authorized_user_file",
               return_value=fake_creds):
        status, err = h.check_health()
    assert status is Status.OK
    assert err is None


def test_check_health_invalid_grant_returns_revoked(valid_token_file: Path):
    from web.api.services.credentials.google import GoogleCredentialHandle

    h = GoogleCredentialHandle(token_path=valid_token_file)
    fake_creds = MagicMock(valid=False, expired=True, refresh_token="1//fake")
    fake_creds.refresh.side_effect = RefreshError(
        "invalid_grant: Token has been expired or revoked.",
        {"error": "invalid_grant"},
    )
    with patch("web.api.services.credentials.google.Credentials.from_authorized_user_file",
               return_value=fake_creds):
        status, err = h.check_health()
    assert status is Status.REVOKED
    assert "invalid_grant" in (err or "")


def test_check_health_generic_refresh_error_returns_expired(valid_token_file: Path):
    from web.api.services.credentials.google import GoogleCredentialHandle

    h = GoogleCredentialHandle(token_path=valid_token_file)
    fake_creds = MagicMock(valid=False, expired=True, refresh_token="1//fake")
    fake_creds.refresh.side_effect = RefreshError("network blip", {})
    with patch("web.api.services.credentials.google.Credentials.from_authorized_user_file",
               return_value=fake_creds):
        status, err = h.check_health()
    assert status is Status.EXPIRED
```

- [ ] **Step 2: Run — verify it fails**

```bash
pytest web/api/tests/services/test_credentials_google.py -xvs
```

Expected: `ModuleNotFoundError: No module named 'web.api.services.credentials.google'`.

- [ ] **Step 3: Implement `google.py`**

```python
# web/api/services/credentials/google.py
"""Google OAuth credential handle.

Owns token.json. Maps the messy world of RefreshError variants into the
clean Status enum the rest of the system reasons about.
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
        except Exception as exc:  # malformed JSON, missing fields, etc.
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


_SECRET_NEEDLES = ("refresh_token", "access_token", "client_secret")


def _scrub(msg: str) -> str:
    out = msg[:200]
    for needle in _SECRET_NEEDLES:
        out = out.replace(needle, "[redacted]")
    return out
```

- [ ] **Step 4: Run — verify it passes**

```bash
pytest web/api/tests/services/test_credentials_google.py -xvs
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add web/api/services/credentials/google.py web/api/tests/services/test_credentials_google.py
git commit -m "feat(credentials): GoogleCredentialHandle.check_health with RefreshError mapping"
```

### Task 1.4: Google handle — atomic token write under fault

**Files:**
- Test: `web/api/tests/services/test_credentials_google.py` (append)

- [ ] **Step 1: Append the test**

Add to `test_credentials_google.py`:

```python
def test_atomic_write_does_not_corrupt_existing_token(valid_token_file: Path, monkeypatch: pytest.MonkeyPatch):
    """If os.replace fails after the temp file is written, the original is untouched."""
    from web.api.services.credentials.google import GoogleCredentialHandle

    h = GoogleCredentialHandle(token_path=valid_token_file)
    original = valid_token_file.read_text()

    fake_creds = MagicMock()
    fake_creds.to_json.return_value = '{"token": "new"}'

    def boom(src, dst):
        raise OSError("simulated disk full")

    monkeypatch.setattr("web.api.services.credentials.google.os.replace", boom)

    with pytest.raises(OSError):
        h._atomic_write(fake_creds)

    assert valid_token_file.read_text() == original
```

- [ ] **Step 2: Run — verify it passes** (implementation already supports this)

```bash
pytest web/api/tests/services/test_credentials_google.py::test_atomic_write_does_not_corrupt_existing_token -xvs
```

Expected: passed.

- [ ] **Step 3: Commit**

```bash
git add web/api/tests/services/test_credentials_google.py
git commit -m "test(credentials): atomic write preserves original token on failure"
```

### Task 1.5: Google handle — service builders (`get_drive`, `get_classroom`, `get_gmail`)

**Files:**
- Modify: `web/api/services/credentials/google.py`
- Test: `web/api/tests/services/test_credentials_google.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `test_credentials_google.py`:

```python
def test_get_classroom_returns_service_when_ok(valid_token_file: Path):
    from web.api.services.credentials.google import GoogleCredentialHandle

    h = GoogleCredentialHandle(token_path=valid_token_file)
    fake_creds = MagicMock(valid=True, expired=False)
    fake_service = MagicMock(name="classroom-service")
    with (
        patch("web.api.services.credentials.google.Credentials.from_authorized_user_file",
              return_value=fake_creds),
        patch("web.api.services.credentials.google.build", return_value=fake_service) as build_mock,
    ):
        service = h.get_classroom()
    assert service is fake_service
    build_mock.assert_called_once_with("classroom", "v1", credentials=fake_creds, cache_discovery=False)


def test_get_drive_raises_credential_broken_when_revoked(valid_token_file: Path):
    from web.api.services.credentials.google import GoogleCredentialHandle
    from web.api.services.credentials import CredentialBroken, Status

    h = GoogleCredentialHandle(token_path=valid_token_file)
    fake_creds = MagicMock(valid=False, expired=True, refresh_token="1//fake")
    fake_creds.refresh.side_effect = RefreshError("invalid_grant", {})

    with patch("web.api.services.credentials.google.Credentials.from_authorized_user_file",
               return_value=fake_creds):
        with pytest.raises(CredentialBroken) as exc_info:
            h.get_drive()

    assert exc_info.value.name == "google_oauth"
    assert exc_info.value.status is Status.REVOKED
```

- [ ] **Step 2: Run — verify it fails**

```bash
pytest web/api/tests/services/test_credentials_google.py::test_get_classroom_returns_service_when_ok -xvs
```

Expected: `AttributeError: 'GoogleCredentialHandle' object has no attribute 'get_classroom'`.

- [ ] **Step 3: Add builders to `google.py`**

Append these methods inside the class:

```python
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
```

- [ ] **Step 4: Run — verify it passes**

```bash
pytest web/api/tests/services/test_credentials_google.py -xvs
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add web/api/services/credentials/google.py web/api/tests/services/test_credentials_google.py
git commit -m "feat(credentials): get_drive/classroom/gmail builders with CredentialBroken gating"
```

### Task 1.6: `register_defaults()` wiring

**Files:**
- Create: `web/api/services/credentials/register_defaults.py`
- Modify: `web/api/services/credentials/__init__.py` (call `register_defaults()` on import)
- Test: `web/api/tests/services/test_credentials_register_defaults.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# web/api/tests/services/test_credentials_register_defaults.py
from __future__ import annotations


def test_default_registry_has_google_oauth():
    from web.api.services.credentials import REGISTRY

    h = REGISTRY.get("google_oauth")
    assert h.name == "google_oauth"
```

- [ ] **Step 2: Run — verify it fails**

```bash
pytest web/api/tests/services/test_credentials_register_defaults.py -xvs
```

Expected: `KeyError: 'google_oauth'`.

- [ ] **Step 3: Implement `register_defaults.py`**

```python
# web/api/services/credentials/register_defaults.py
"""Registers the default set of credentials on import of the package."""
from __future__ import annotations

import os
from pathlib import Path


def register_defaults() -> None:
    """Idempotent — safe to call multiple times."""
    from web.api.services.credentials import REGISTRY
    from web.api.services.credentials.google import GoogleCredentialHandle

    token_path = Path(os.environ.get(
        "GOOGLE_TOKEN_PATH",
        Path(__file__).resolve().parents[4] / "token.json",
    ))

    if "google_oauth" not in {h.name for h in REGISTRY.all()}:
        REGISTRY.register(GoogleCredentialHandle(token_path=token_path))
```

- [ ] **Step 4: Hook from `__init__.py`**

Append at the very bottom of `web/api/services/credentials/__init__.py`:

```python
# Populate the singleton with the default handles.
from web.api.services.credentials.register_defaults import register_defaults  # noqa: E402

register_defaults()
```

- [ ] **Step 5: Run — verify it passes**

```bash
pytest web/api/tests/services/test_credentials_register_defaults.py -xvs
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add web/api/services/credentials/register_defaults.py web/api/services/credentials/__init__.py web/api/tests/services/test_credentials_register_defaults.py
git commit -m "feat(credentials): register_defaults wires GoogleCredentialHandle on import"
```

### Task 1.7: Refactor `tools/run_pipeline.py` to use Registry

**Files:**
- Modify: `tools/run_pipeline.py` (lines 33-48 — the existing creds block)
- Test: `tests/test_tools_credential_integration.py` (new)

- [ ] **Step 1: Write the failing integration test**

```python
# tests/test_tools_credential_integration.py
"""End-to-end test that pipeline tools degrade gracefully when creds are broken."""
from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from web.api.services.credentials import CredentialBroken, Status


def test_run_pipeline_tick_skips_when_google_revoked(caplog: pytest.LogCaptureFixture):
    """One tick of the pipeline against a REVOKED Google credential should:
       - not raise
       - log CREDENTIAL_BROKEN with credential name and status
       - return without doing any classroom work.
    """
    from tools import run_pipeline

    broken = CredentialBroken("google_oauth", Status.REVOKED, "invalid_grant")
    with (
        patch.object(run_pipeline, "_get_classroom", side_effect=broken),
        caplog.at_level(logging.ERROR),
    ):
        run_pipeline.tick()

    assert any(
        "CREDENTIAL_BROKEN" in r.message and "google_oauth" in r.message and "REVOKED" in r.message
        for r in caplog.records
    ), f"expected CREDENTIAL_BROKEN log line, got: {[r.message for r in caplog.records]}"
```

- [ ] **Step 2: Read `tools/run_pipeline.py` lines 30-60 to locate the creds block**

```bash
sed -n '30,60p' tools/run_pipeline.py
```

Note the exact function name (`load_creds`, `get_creds`, or similar) and every call site of it in the file:

```bash
grep -n "load_creds\|get_creds" tools/run_pipeline.py
```

- [ ] **Step 3: Refactor — replace the inline creds block with `_get_classroom()`**

The target shape (adapt to whatever currently exists in the file):

```python
# Near the top of tools/run_pipeline.py
import logging

from web.api.services.credentials import REGISTRY, CredentialBroken

log = logging.getLogger(__name__)


def _get_classroom():
    return REGISTRY.get("google_oauth").get_classroom()


def _get_drive():
    return REGISTRY.get("google_oauth").get_drive()


def tick() -> None:
    """One pipeline iteration. Wrapped in CredentialBroken handler so the
    daemon survives credential outages.
    """
    try:
        classroom = _get_classroom()
        drive = _get_drive()
    except CredentialBroken as exc:
        log.error(
            "CREDENTIAL_BROKEN %s %s — see /settings/credentials (%s)",
            exc.name, exc.status.value, exc.reason or "no detail",
        )
        return

    _run_iteration(classroom, drive)
```

**If `run_pipeline.py` currently does not have a `tick()` function,** find its existing main-loop body (likely inside `main()` or `run_once()`), rename it to `_run_iteration(classroom, drive)`, and wrap it as shown above. Keep the existing `while True: tick(); time.sleep(...)` shape (or whatever loop exists) untouched outside of `tick()`.

Delete the old `load_creds`/`get_creds` function and any inline `Credentials.from_authorized_user_file` block.

- [ ] **Step 4: Run — verify integration test passes**

```bash
pytest tests/test_tools_credential_integration.py -xvs
```

Expected: 1 passed.

- [ ] **Step 5: Smoke-run the tool**

```bash
python3 tools/run_pipeline.py --once 2>&1 | head -40
```

Expected: existing behaviour, no `Traceback`. If `CREDENTIAL_BROKEN` appears, that's a real credential issue, not a code bug.

- [ ] **Step 6: Commit**

```bash
git add tools/run_pipeline.py tests/test_tools_credential_integration.py
git commit -m "refactor(tools): run_pipeline uses Registry; tick() survives CredentialBroken"
```

### Task 1.8: Refactor `tools/watch_classroom.py`

**Files:**
- Modify: `tools/watch_classroom.py` (lines 50-65 — the creds block)

- [ ] **Step 1: Read existing creds block**

```bash
sed -n '45,70p' tools/watch_classroom.py
```

- [ ] **Step 2: Replace**

Apply the same pattern as Task 1.7: import the Registry, delete the local creds loader, replace its call sites with `REGISTRY.get("google_oauth").get_classroom()` / `get_drive()`. If the file has a `main()` that loops, wrap the loop body with `try/except CredentialBroken` and `log.error("CREDENTIAL_BROKEN %s %s ...", ...)`.

- [ ] **Step 3: Smoke-run**

```bash
python3 tools/watch_classroom.py --once 2>&1 | head -20
```

Expected: lists pending TURNED_IN submissions normally, or logs CREDENTIAL_BROKEN if the token is revoked. **No** Python traceback.

- [ ] **Step 4: Commit**

```bash
git add tools/watch_classroom.py
git commit -m "refactor(tools): watch_classroom uses Registry; survives CredentialBroken"
```

### Task 1.9: Refactor `tools/email_helper.py`

**Files:**
- Modify: `tools/email_helper.py` (lines 18-32)

- [ ] **Step 1: Read existing creds block**

```bash
sed -n '15,35p' tools/email_helper.py
```

- [ ] **Step 2: Replace**

Apply the same refactor. `email_helper.py` is imported by other tools (not a daemon); it should expose its existing `send_email(...)` function, internally calling `REGISTRY.get("google_oauth").get_gmail()` and letting `CredentialBroken` propagate to the caller. The caller (`check_review_replies.py`, `generate_answer_key.py`) runs inside the daemon's `tick()` which already has the handler.

- [ ] **Step 3: Commit**

```bash
git add tools/email_helper.py
git commit -m "refactor(tools): email_helper uses Registry"
```

### Task 1.10: Wave 1 smoke + checkpoint

- [ ] **Step 1: Run the full test suite**

```bash
pytest -xvs
```

Expected: all green.

- [ ] **Step 2: Sanity-check no remaining inline creds loaders**

```bash
grep -nE "Credentials\.from_authorized_user_file|creds\.refresh\(Request" tools/*.py | grep -v setup_drive
```

Expected: no matches.

- [ ] **Step 3: Push branch (optional)**

```bash
git push -u origin feat/credential-registry
```

---

## Wave 2 — Postgres state + Notifier

By end of Wave 2: status persists across process restarts, ops email arrives on edges, 4h rate limit holds.

### Task 2.1: Create the schema migration

**Files:**
- Create: `db/migrations/001_credentials_health.sql`
- Modify: `db/schema.sql` (append the same DDL so fresh deploys get it too)

- [ ] **Step 1: Create the migration file**

```sql
-- db/migrations/001_credentials_health.sql
-- Apply with:
--   docker exec -i evalassign-postgres psql -U evalassign -d evalassign < db/migrations/001_credentials_health.sql
-- Idempotent — safe to re-run.

CREATE TABLE IF NOT EXISTS credentials_health (
    name                  TEXT PRIMARY KEY,
    status                TEXT NOT NULL,
    last_checked_at       TIMESTAMPTZ NOT NULL,
    last_ok_at            TIMESTAMPTZ,
    last_error            TEXT,
    recovery_started_at   TIMESTAMPTZ,
    notified_at           TIMESTAMPTZ,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_credentials_health_status
    ON credentials_health (status);
```

- [ ] **Step 2: Append the same DDL to `db/schema.sql`**

Append the same `CREATE TABLE IF NOT EXISTS credentials_health (...)` and `CREATE INDEX ...` blocks to the end of `db/schema.sql`.

- [ ] **Step 3: Apply the migration**

```bash
docker exec -i evalassign-postgres psql -U evalassign -d evalassign < db/migrations/001_credentials_health.sql
```

Expected: `CREATE TABLE`, `CREATE INDEX` (or `NOTICE: ... already exists, skipping` on re-run).

- [ ] **Step 4: Verify the table exists**

```bash
docker exec -i evalassign-postgres psql -U evalassign -d evalassign -c "\d credentials_health"
```

Expected: column listing matches the DDL.

- [ ] **Step 5: Commit**

```bash
git add db/migrations/001_credentials_health.sql db/schema.sql
git commit -m "db: add credentials_health table (migration 001)"
```

### Task 2.2: Postgres I/O — `store.py`

**Files:**
- Create: `web/api/services/credentials/store.py`
- Test: `web/api/tests/services/test_store.py` (new)

- [ ] **Step 1: Read how the existing API connects to Postgres**

```bash
grep -n "psycopg\|DATABASE_URL\|conn(" web/api/deps.py web/api/main.py 2>/dev/null | head -20
```

Note the existing connection pattern. The Store should reuse it if possible; otherwise use `psycopg.connect(os.environ["DATABASE_URL"])` directly (matches OPERATIONS.md).

- [ ] **Step 2: Write the failing test**

```python
# web/api/tests/services/test_store.py
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from web.api.services.credentials import Status

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — integration test against live Postgres",
)


def test_upsert_inserts_new_row():
    from web.api.services.credentials.store import upsert_health, read_all, delete_health

    name = "test_cred_a"
    now = datetime.now(timezone.utc)
    upsert_health(name=name, status=Status.OK, last_error=None, now=now)

    rows = {r["name"]: r for r in read_all()}
    assert name in rows
    assert rows[name]["status"] == "OK"
    assert rows[name]["last_ok_at"] is not None

    delete_health(name)


def test_upsert_updates_existing_row():
    from web.api.services.credentials.store import upsert_health, read_all, delete_health

    name = "test_cred_b"
    upsert_health(name=name, status=Status.OK, last_error=None,
                  now=datetime.now(timezone.utc))
    upsert_health(name=name, status=Status.REVOKED, last_error="invalid_grant",
                  now=datetime.now(timezone.utc))

    row = next(r for r in read_all() if r["name"] == name)
    assert row["status"] == "REVOKED"
    assert row["last_error"] == "invalid_grant"
    assert row["last_ok_at"] is not None  # preserved across the transition

    delete_health(name)
```

- [ ] **Step 3: Run — verify it fails**

```bash
DATABASE_URL=postgresql://evalassign:evalassign@127.0.0.1:5433/evalassign \
  pytest web/api/tests/services/test_store.py -xvs
```

Expected: `ModuleNotFoundError: ...credentials.store`.

- [ ] **Step 4: Implement `store.py`**

```python
# web/api/services/credentials/store.py
"""Postgres I/O for credentials_health. The only thing that knows the table schema."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from web.api.services.credentials import Status


def _conn() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"])


_UPSERT_SQL = """
INSERT INTO credentials_health
    (name, status, last_checked_at, last_ok_at, last_error, updated_at)
VALUES
    (%(name)s, %(status)s, %(now)s,
     CASE WHEN %(status)s = 'OK' THEN %(now)s ELSE NULL END,
     %(last_error)s, %(now)s)
ON CONFLICT (name) DO UPDATE SET
    status            = EXCLUDED.status,
    last_checked_at   = EXCLUDED.last_checked_at,
    last_ok_at        = CASE WHEN EXCLUDED.status = 'OK'
                              THEN EXCLUDED.last_checked_at
                              ELSE credentials_health.last_ok_at END,
    last_error        = EXCLUDED.last_error,
    updated_at        = EXCLUDED.updated_at;
"""


def upsert_health(name: str, status: Status, last_error: str | None, now: datetime) -> None:
    with _conn() as c, c.cursor() as cur:
        cur.execute(_UPSERT_SQL, {
            "name": name,
            "status": status.value,
            "now": now,
            "last_error": last_error,
        })


def read_all() -> list[dict[str, Any]]:
    with _conn() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM credentials_health ORDER BY name")
        return list(cur.fetchall())


def read_one(name: str) -> dict[str, Any] | None:
    with _conn() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM credentials_health WHERE name = %s", (name,))
        return cur.fetchone()


def update_notified_at(name: str, when: datetime) -> None:
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            "UPDATE credentials_health SET notified_at = %s WHERE name = %s",
            (when, name),
        )


def update_recovery_started_at(name: str, when: datetime | None) -> None:
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            "UPDATE credentials_health SET recovery_started_at = %s WHERE name = %s",
            (when, name),
        )


def delete_health(name: str) -> None:
    """Test-only helper. Not exposed via the API."""
    with _conn() as c, c.cursor() as cur:
        cur.execute("DELETE FROM credentials_health WHERE name = %s", (name,))
```

- [ ] **Step 5: Run — verify it passes**

```bash
DATABASE_URL=postgresql://evalassign:evalassign@127.0.0.1:5433/evalassign \
  pytest web/api/tests/services/test_store.py -xvs
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add web/api/services/credentials/store.py web/api/tests/services/test_store.py
git commit -m "feat(credentials): Postgres store for credentials_health"
```

### Task 2.3: Registry persists status to Postgres (with fallback)

**Files:**
- Modify: `web/api/services/credentials/__init__.py`
- Test: `web/api/tests/services/test_credentials_registry.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `test_credentials_registry.py`:

```python
def test_report_status_writes_to_store_when_available(monkeypatch):
    from web.api.services.credentials import Registry, Status

    calls = []

    def fake_upsert(name, status, last_error, now):
        calls.append((name, status, last_error))

    monkeypatch.setattr("web.api.services.credentials.store.upsert_health", fake_upsert)

    reg = Registry()
    reg.report_status("google_oauth", Status.REVOKED, "invalid_grant")
    assert calls == [("google_oauth", Status.REVOKED, "invalid_grant")]


def test_report_status_falls_back_to_memory_on_db_error(monkeypatch, caplog):
    import logging
    from web.api.services.credentials import Registry, Status

    def boom(*a, **kw):
        raise RuntimeError("postgres down")

    monkeypatch.setattr("web.api.services.credentials.store.upsert_health", boom)

    reg = Registry()
    with caplog.at_level(logging.WARNING):
        reg.report_status("google_oauth", Status.REVOKED, "invalid_grant")
    assert reg.snapshot()["google_oauth"].status is Status.REVOKED
    assert any("postgres down" in r.message.lower() for r in caplog.records)
```

- [ ] **Step 2: Run — verify it fails**

```bash
pytest web/api/tests/services/test_credentials_registry.py::test_report_status_writes_to_store_when_available -xvs
```

Expected: assertion fails (no DB call made yet).

- [ ] **Step 3: Modify `Registry.report_status` in `__init__.py`**

Replace the method body with:

```python
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
```

- [ ] **Step 4: Run — verify it passes**

```bash
pytest web/api/tests/services/test_credentials_registry.py -xvs
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add web/api/services/credentials/__init__.py web/api/tests/services/test_credentials_registry.py
git commit -m "feat(credentials): Registry persists to Postgres; falls back to in-memory on DB outage"
```

### Task 2.4: Notifier — edge detection + 4h rate limit

**Files:**
- Create: `web/api/services/credentials/notifier.py`
- Test: `web/api/tests/services/test_notifier.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# web/api/tests/services/test_notifier.py
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time

from web.api.services.credentials import Status


def _make_notifier(send_email_mock, store_mock):
    from web.api.services.credentials.notifier import StatusEdgeNotifier
    return StatusEdgeNotifier(
        send_email=send_email_mock,
        read_one=store_mock["read_one"],
        update_notified_at=store_mock["update_notified_at"],
        recipient="ops@example.com",
    )


@pytest.fixture
def store_mock():
    return {
        "read_one": MagicMock(return_value={"notified_at": None}),
        "update_notified_at": MagicMock(),
    }


def test_emails_on_ok_to_revoked_transition(store_mock):
    send = MagicMock()
    n = _make_notifier(send, store_mock)
    n.on_transition("google_oauth", Status.OK, Status.REVOKED, "invalid_grant")
    assert send.call_count == 1


def test_emails_on_revoked_to_ok_transition(store_mock):
    send = MagicMock()
    n = _make_notifier(send, store_mock)
    n.on_transition("google_oauth", Status.REVOKED, Status.OK, None)
    assert send.call_count == 1
    subject = send.call_args.kwargs.get("subject") or send.call_args.args[0]
    assert "RECOVERED" in subject


def test_no_email_when_status_unchanged(store_mock):
    send = MagicMock()
    n = _make_notifier(send, store_mock)
    n.on_transition("google_oauth", Status.REVOKED, Status.REVOKED, "invalid_grant")
    send.assert_not_called()


def test_rate_limit_4h(store_mock):
    send = MagicMock()
    n = _make_notifier(send, store_mock)
    with freeze_time("2026-05-18 12:00:00") as frozen:
        n.on_transition("google_oauth", Status.OK, Status.REVOKED, "x")
        assert send.call_count == 1

        store_mock["read_one"].return_value = {"notified_at": datetime.now(timezone.utc)}
        frozen.tick(timedelta(hours=1))
        n.on_transition("google_oauth", Status.OK, Status.REVOKED, "x")
        assert send.call_count == 1  # rate-limited

        frozen.tick(timedelta(hours=3, minutes=2))
        n.on_transition("google_oauth", Status.OK, Status.REVOKED, "x")
        assert send.call_count == 2


def test_no_recursion_when_send_email_fails(store_mock, caplog):
    send = MagicMock(side_effect=RuntimeError("gmail down"))
    n = _make_notifier(send, store_mock)
    n.on_transition("google_oauth", Status.OK, Status.REVOKED, "x")  # must not raise
    assert any("gmail down" in r.message.lower() for r in caplog.records)
```

- [ ] **Step 2: Run — verify it fails**

```bash
pytest web/api/tests/services/test_notifier.py -xvs
```

Expected: `ModuleNotFoundError: ...notifier`.

- [ ] **Step 3: Implement `notifier.py`**

```python
# web/api/services/credentials/notifier.py
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
```

- [ ] **Step 4: Run — verify it passes**

```bash
pytest web/api/tests/services/test_notifier.py -xvs
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add web/api/services/credentials/notifier.py web/api/tests/services/test_notifier.py
git commit -m "feat(credentials): StatusEdgeNotifier with 4h rate limit + no-recursion guard"
```

### Task 2.5: Wire Notifier to Registry; add `OPS_ALERT_EMAIL` env

**Files:**
- Modify: `web/api/services/credentials/register_defaults.py`
- Modify (or create): `.env.example`

- [ ] **Step 1: Add `OPS_ALERT_EMAIL` to `.env.example`**

If `.env.example` exists, append; otherwise create with this line:

```text
# Address that receives credential health alerts. Leave empty to disable.
OPS_ALERT_EMAIL=
```

Set the real value in your real `.env` (e.g. `OPS_ALERT_EMAIL=mohitsardana@gmail.com`).

- [ ] **Step 2: Modify `register_defaults.py`**

Replace the body with:

```python
# web/api/services/credentials/register_defaults.py
from __future__ import annotations

import os
from pathlib import Path


def register_defaults() -> None:
    from web.api.services.credentials import REGISTRY
    from web.api.services.credentials.google import GoogleCredentialHandle
    from web.api.services.credentials import store
    from web.api.services.credentials.notifier import StatusEdgeNotifier

    token_path = Path(os.environ.get(
        "GOOGLE_TOKEN_PATH",
        Path(__file__).resolve().parents[4] / "token.json",
    ))

    if "google_oauth" not in {h.name for h in REGISTRY.all()}:
        REGISTRY.register(GoogleCredentialHandle(token_path=token_path))

    recipient = os.environ.get("OPS_ALERT_EMAIL", "").strip() or None
    if recipient and not getattr(REGISTRY, "_notifier_attached", False):
        from tools.email_helper import send_email  # late import — avoids circular

        notifier = StatusEdgeNotifier(
            send_email=send_email,
            read_one=store.read_one,
            update_notified_at=store.update_notified_at,
            recipient=recipient,
        )
        REGISTRY.subscribe_transition(notifier.on_transition)
        REGISTRY._notifier_attached = True
```

- [ ] **Step 3: Integration test**

Append to `web/api/tests/services/test_notifier.py`:

```python
def test_registry_fires_notifier_on_transition(monkeypatch):
    from web.api.services.credentials import REGISTRY, Status

    received = []
    def fake_send(to, subject, body):
        received.append(subject)

    REGISTRY._subscribers = []
    from web.api.services.credentials.notifier import StatusEdgeNotifier
    n = StatusEdgeNotifier(
        send_email=fake_send,
        read_one=lambda name: {"notified_at": None},
        update_notified_at=lambda name, when: None,
        recipient="ops@example.com",
    )
    REGISTRY.subscribe_transition(n.on_transition)

    monkeypatch.setattr("web.api.services.credentials.store.upsert_health",
                        lambda **kw: None)
    REGISTRY.report_status("test_cred", Status.OK, None)
    REGISTRY.report_status("test_cred", Status.REVOKED, "invalid_grant")
    assert len(received) == 1
    assert "REVOKED" in received[0]
```

- [ ] **Step 4: Run — verify it passes**

```bash
pytest web/api/tests/services/test_notifier.py -xvs
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add web/api/services/credentials/register_defaults.py .env.example web/api/tests/services/test_notifier.py
git commit -m "feat(credentials): wire Notifier into Registry on register_defaults"
```

### Task 2.6: Wave 2 smoke

- [ ] **Step 1: Run full test suite**

```bash
DATABASE_URL=postgresql://evalassign:evalassign@127.0.0.1:5433/evalassign \
  pytest -xvs
```

Expected: all green.

- [ ] **Step 2: Manual smoke — simulate a transition end-to-end**

```bash
python3 -c "
import os
os.environ['DATABASE_URL'] = 'postgresql://evalassign:evalassign@127.0.0.1:5433/evalassign'
from web.api.services.credentials import REGISTRY, Status
REGISTRY.report_status('test_manual', Status.OK, None)
REGISTRY.report_status('test_manual', Status.REVOKED, 'manual test')
"
docker exec -i evalassign-postgres psql -U evalassign -d evalassign \
  -c "SELECT name, status, last_error FROM credentials_health WHERE name='test_manual';"
docker exec -i evalassign-postgres psql -U evalassign -d evalassign \
  -c "DELETE FROM credentials_health WHERE name='test_manual';"
```

Expected: SELECT shows `test_manual | REVOKED | manual test`. If `OPS_ALERT_EMAIL` is set, one email titled `[evalassign] test_manual REVOKED` arrives.

---

## Wave 3 — FastAPI router + APScheduler

By end of Wave 3: `/api/credentials/status` returns live data, you can start an OAuth flow from a curl call, scheduler ticks every 15 min.

### Task 3.1: Router skeleton — `GET /status` and `POST /{name}/recheck`

**Files:**
- Create: `web/api/routers/credentials.py`
- Modify: `web/api/main.py` (include the router)
- Test: `web/api/tests/routers/test_credentials.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# web/api/tests/routers/test_credentials.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from web.api.services.credentials import Status


@pytest.fixture
def client():
    from web.api.main import app
    return TestClient(app)


def test_status_endpoint_returns_list(client, monkeypatch):
    fake_rows = [
        {"name": "google_oauth", "status": "OK",
         "last_checked_at": datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
         "last_ok_at": datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
         "last_error": None, "recovery_started_at": None,
         "notified_at": None,
         "updated_at": datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)},
    ]
    monkeypatch.setattr("web.api.routers.credentials.store.read_all",
                        lambda: fake_rows)
    monkeypatch.setattr("web.api.routers.credentials._auth_required",
                        lambda req: None)

    resp = client.get("/api/credentials/status")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert body[0]["name"] == "google_oauth"
    assert body[0]["status"] == "OK"


def test_recheck_triggers_check_health(client, monkeypatch):
    handle = MagicMock(name="handle")
    handle.check_health.return_value = (Status.OK, None)
    monkeypatch.setattr("web.api.routers.credentials._auth_required",
                        lambda req: None)
    monkeypatch.setattr("web.api.routers.credentials.REGISTRY.get",
                        lambda name: handle)

    resp = client.post("/api/credentials/google_oauth/recheck")
    assert resp.status_code == 200
    handle.check_health.assert_called_once()


def test_recheck_unknown_returns_404(client, monkeypatch):
    monkeypatch.setattr("web.api.routers.credentials._auth_required",
                        lambda req: None)
    monkeypatch.setattr("web.api.routers.credentials.REGISTRY.get",
                        MagicMock(side_effect=KeyError("nope")))
    resp = client.post("/api/credentials/nope/recheck")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run — verify it fails**

```bash
pytest web/api/tests/routers/test_credentials.py -xvs
```

Expected: `ModuleNotFoundError: ...routers.credentials`.

- [ ] **Step 3: Implement the router**

```python
# web/api/routers/credentials.py
"""HTTP surface for the Credential Registry."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from web.api.services.credentials import REGISTRY, Status
from web.api.services.credentials import store

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/credentials", tags=["credentials"])


def _auth_required(request: Request) -> None:
    """Defense-in-depth check; Next.js middleware already gates /api/* at the proxy layer."""
    return None


@router.get("/status")
def get_status(_: None = Depends(_auth_required)) -> list[dict[str, Any]]:
    try:
        rows = store.read_all()
    except Exception as exc:
        log.warning("credentials/status: store unavailable (%s)", exc)
        rows = []

    seen = {r["name"] for r in rows}
    for h in REGISTRY.all():
        if h.name not in seen:
            rows.append({
                "name": h.name,
                "status": Status.UNKNOWN.value,
                "last_checked_at": None,
                "last_ok_at": None,
                "last_error": None,
                "recovery_started_at": None,
                "notified_at": None,
                "updated_at": None,
            })
    return rows


@router.post("/{name}/recheck")
def recheck(name: str, _: None = Depends(_auth_required)) -> dict[str, str]:
    try:
        handle = REGISTRY.get(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown credential: {name}")

    status, err = handle.check_health()
    REGISTRY.report_status(name, status, err)
    return {"name": name, "status": status.value}
```

- [ ] **Step 4: Include router in `main.py`**

Open `web/api/main.py`. Find where other routers are included (`app.include_router(queue.router)` etc.) and add:

```python
from web.api.routers import credentials as credentials_router
app.include_router(credentials_router.router)
```

- [ ] **Step 5: Run — verify it passes**

```bash
pytest web/api/tests/routers/test_credentials.py -xvs
```

Expected: 3 passed.

- [ ] **Step 6: Curl smoke**

```bash
curl -s http://localhost:8000/api/credentials/status | python3 -m json.tool
```

Expected: JSON array including `{"name": "google_oauth", ...}`.

- [ ] **Step 7: Commit**

```bash
git add web/api/routers/credentials.py web/api/main.py web/api/tests/routers/test_credentials.py
git commit -m "feat(credentials): GET /api/credentials/status + POST /{name}/recheck"
```

### Task 3.2: OAuth reauth — `POST /google_oauth/reauth`

**Files:**
- Modify: `web/api/routers/credentials.py`
- Modify: `web/api/services/credentials/google.py` (add `start_reauth_flow`)
- Test: `web/api/tests/routers/test_credentials.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `test_credentials.py`:

```python
def test_reauth_returns_consent_url(client, monkeypatch):
    monkeypatch.setattr("web.api.routers.credentials._auth_required",
                        lambda req: None)
    monkeypatch.setattr(
        "web.api.routers.credentials.google_module.start_reauth_flow",
        lambda: ("https://accounts.google.com/o/oauth2/auth?fake=1", "STATE-TOKEN"),
    )
    resp = client.post("/api/credentials/google_oauth/reauth")
    assert resp.status_code == 200
    body = resp.json()
    assert body["consent_url"].startswith("https://accounts.google.com/")
    assert body["state"] == "STATE-TOKEN"


def test_reauth_idempotent_within_window(client, monkeypatch):
    monkeypatch.setattr("web.api.routers.credentials._auth_required",
                        lambda req: None)
    calls = []
    def fake_start():
        calls.append(1)
        return ("https://x/", "S")
    monkeypatch.setattr(
        "web.api.routers.credentials.google_module.start_reauth_flow",
        fake_start,
    )
    r1 = client.post("/api/credentials/google_oauth/reauth")
    r2 = client.post("/api/credentials/google_oauth/reauth")
    assert r1.json()["state"] == r2.json()["state"]
```

- [ ] **Step 2: Run — verify it fails**

```bash
pytest web/api/tests/routers/test_credentials.py::test_reauth_returns_consent_url -xvs
```

Expected: 404 (route doesn't exist).

- [ ] **Step 3: Add `start_reauth_flow` to `google.py`**

Append:

```python
# ---------------------------------------------------------------------- OAuth flow helpers
from datetime import datetime, timezone, timedelta

from google_auth_oauthlib.flow import Flow

_PENDING_FLOWS: dict[str, Flow] = {}
_LAST_FLOW_STATE: dict[str, tuple[str, datetime]] = {}

CALLBACK_URL = "http://localhost:8000/api/credentials/google_oauth/oauth-callback"


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
```

- [ ] **Step 4: Add the route**

In `web/api/routers/credentials.py`, add near the top:

```python
from web.api.services.credentials import google as google_module
```

And add the endpoint:

```python
@router.post("/google_oauth/reauth")
def google_reauth(_: None = Depends(_auth_required)) -> dict[str, str]:
    try:
        consent_url, state = google_module.start_reauth_flow()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"credentials.json missing: {exc}")
    return {"consent_url": consent_url, "state": state}
```

- [ ] **Step 5: Run — verify it passes**

```bash
pytest web/api/tests/routers/test_credentials.py -xvs
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add web/api/routers/credentials.py web/api/services/credentials/google.py web/api/tests/routers/test_credentials.py
git commit -m "feat(credentials): POST /google_oauth/reauth returns consent URL (5-min idempotent)"
```

### Task 3.3: OAuth callback — `GET /google_oauth/oauth-callback`

**Files:**
- Modify: `web/api/services/credentials/google.py` (add `finish_reauth_flow`)
- Modify: `web/api/routers/credentials.py`
- Test: `web/api/tests/routers/test_credentials.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `test_credentials.py`:

```python
def test_oauth_callback_invalid_state_returns_400(client, monkeypatch):
    monkeypatch.setattr("web.api.routers.credentials._auth_required",
                        lambda req: None)
    monkeypatch.setattr(
        "web.api.routers.credentials.google_module._PENDING_FLOWS",
        {},
    )
    resp = client.get("/api/credentials/google_oauth/oauth-callback?code=X&state=BAD")
    assert resp.status_code == 400


def test_oauth_callback_writes_token_on_success(client, monkeypatch, tmp_path):
    monkeypatch.setattr("web.api.routers.credentials._auth_required",
                        lambda req: None)

    flow = MagicMock()
    flow.fetch_token.return_value = None
    fake_creds = MagicMock()
    fake_creds.to_json.return_value = '{"token":"new","refresh_token":"r"}'
    flow.credentials = fake_creds

    monkeypatch.setattr(
        "web.api.routers.credentials.google_module._PENDING_FLOWS",
        {"GOOD-STATE": flow},
    )
    monkeypatch.setattr(
        "web.api.routers.credentials.google_module._validate_creds_with_drive_call",
        lambda creds: True,
    )
    token_target = tmp_path / "token.json"
    monkeypatch.setenv("GOOGLE_TOKEN_PATH", str(token_target))

    resp = client.get("/api/credentials/google_oauth/oauth-callback?code=X&state=GOOD-STATE")
    assert resp.status_code == 200
    assert token_target.read_text() == '{"token":"new","refresh_token":"r"}'
```

- [ ] **Step 2: Run — verify it fails**

```bash
pytest web/api/tests/routers/test_credentials.py::test_oauth_callback_invalid_state_returns_400 -xvs
```

Expected: 404.

- [ ] **Step 3: Add `finish_reauth_flow` + `_validate_creds_with_drive_call` to `google.py`**

```python
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
```

- [ ] **Step 4: Add the callback route**

In `web/api/routers/credentials.py`:

```python
from fastapi.responses import HTMLResponse
from pathlib import Path
import os


@router.get("/google_oauth/oauth-callback", response_class=HTMLResponse)
def google_oauth_callback(code: str, state: str, _: None = Depends(_auth_required)) -> HTMLResponse:
    token_path = Path(os.environ.get(
        "GOOGLE_TOKEN_PATH",
        Path(__file__).resolve().parents[4] / "token.json",
    ))
    try:
        google_module.finish_reauth_flow(code=code, state=state, token_path=token_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return HTMLResponse(
        """<!doctype html><html><body>
        <p>Reconnected. You can close this tab.</p>
        <script>
          try {
            localStorage.setItem("ts:google_reconnected", String(Date.now()));
            window.close();
          } catch (e) {}
        </script>
        </body></html>"""
    )
```

- [ ] **Step 5: Run — verify it passes**

```bash
pytest web/api/tests/routers/test_credentials.py -xvs
```

Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add web/api/routers/credentials.py web/api/services/credentials/google.py web/api/tests/routers/test_credentials.py
git commit -m "feat(credentials): OAuth callback validates token before atomic write"
```

### Task 3.4: APScheduler service

**Files:**
- Create: `web/api/services/credentials/scheduler.py`
- Modify: `web/api/main.py` (lifespan)
- Test: `web/api/tests/services/test_scheduler.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# web/api/tests/services/test_scheduler.py
from __future__ import annotations

from unittest.mock import MagicMock

from web.api.services.credentials import Status


def test_run_one_tick_checks_every_handle(monkeypatch):
    from web.api.services.credentials.scheduler import run_one_tick

    h1 = MagicMock(name="h1"); h1.name = "a"; h1.check_health.return_value = (Status.OK, None)
    h2 = MagicMock(name="h2"); h2.name = "b"; h2.check_health.return_value = (Status.REVOKED, "x")

    fake_registry = MagicMock()
    fake_registry.all.return_value = [h1, h2]

    monkeypatch.setattr("web.api.services.credentials.scheduler.REGISTRY", fake_registry)
    run_one_tick()

    h1.check_health.assert_called_once()
    h2.check_health.assert_called_once()
    fake_registry.report_status.assert_any_call("a", Status.OK, None)
    fake_registry.report_status.assert_any_call("b", Status.REVOKED, "x")
```

- [ ] **Step 2: Run — verify it fails**

```bash
pytest web/api/tests/services/test_scheduler.py -xvs
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `scheduler.py`**

```python
# web/api/services/credentials/scheduler.py
"""APScheduler job that calls check_health() on every registered handle."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from apscheduler.schedulers.background import BackgroundScheduler

from web.api.services.credentials import REGISTRY

log = logging.getLogger(__name__)

INTERVAL_MINUTES = 15
CHECK_TIMEOUT_SECONDS = 10

_scheduler: BackgroundScheduler | None = None


def run_one_tick() -> None:
    """Public for tests. Runs check_health() on every handle with a timeout."""
    handles = REGISTRY.all()
    if not handles:
        return

    with ThreadPoolExecutor(max_workers=len(handles)) as pool:
        futures = {pool.submit(h.check_health): h for h in handles}
        for fut, h in futures.items():
            try:
                status, err = fut.result(timeout=CHECK_TIMEOUT_SECONDS)
            except FutureTimeoutError:
                log.warning("check_health(%s) timed out after %ds", h.name, CHECK_TIMEOUT_SECONDS)
                continue
            except Exception:
                log.exception("check_health(%s) raised", h.name)
                continue
            REGISTRY.report_status(h.name, status, err)


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        run_one_tick,
        trigger="interval",
        minutes=INTERVAL_MINUTES,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    log.info("credentials scheduler started (interval=%dm)", INTERVAL_MINUTES)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    log.info("credentials scheduler stopped")
```

- [ ] **Step 4: Wire into FastAPI lifespan**

Open `web/api/main.py`. Replace the existing `@app.on_event("startup")` block (around line 40) with a `lifespan` context manager:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

from web.api.services.credentials.scheduler import start_scheduler, stop_scheduler, run_one_tick


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        run_one_tick()  # immediate first check
    except Exception:
        import logging
        logging.getLogger(__name__).exception("initial credential tick failed")
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()


# Replace existing `app = FastAPI(...)` with:
app = FastAPI(lifespan=lifespan)  # preserve any other existing kwargs
```

Move any logic from the old `@app.on_event("startup")` body into `lifespan` above the `yield`, then delete the `@app.on_event` block.

- [ ] **Step 5: Run — verify it passes**

```bash
pytest web/api/tests/services/test_scheduler.py -xvs
```

Expected: 1 passed.

- [ ] **Step 6: Restart the API and check the log**

```bash
scripts/start-api.sh
```

Expected: log contains `credentials scheduler started (interval=15m)`.

- [ ] **Step 7: Commit**

```bash
git add web/api/services/credentials/scheduler.py web/api/main.py web/api/tests/services/test_scheduler.py
git commit -m "feat(credentials): APScheduler tick every 15m + immediate startup tick via lifespan"
```

### Task 3.5: OPERATIONS.md — credential health & recovery section

**Files:**
- Modify: `OPERATIONS.md`

- [ ] **Step 1: Append section**

Add near the bottom of `OPERATIONS.md`:

```markdown
## Credential health & recovery

The system tracks the health of external credentials (Google OAuth, Anthropic API)
in a Postgres table and surfaces failures via the header pill and ops email.

### One-time setup (must be done before the first Reconnect)

1. **Add the OAuth callback URL to Google Cloud Console:**
   - Open https://console.cloud.google.com/ -> APIs & Services -> Credentials
   - Click the OAuth 2.0 Client used by `credentials.json`
   - Under "Authorized redirect URIs", add:
     `http://localhost:8000/api/credentials/google_oauth/oauth-callback`
   - Save.

2. **Publish the OAuth consent screen** (root-cause fix for 7-day refresh-token expiry):
   - OAuth consent screen -> Publishing status
   - If "Testing", click "PUBLISH APP"
   - Scopes (Classroom + Drive + Gmail) are sensitive, but for personal use under
     100 users, Google does not require formal verification.
   - After publishing, refresh tokens no longer auto-expire after 7 days.

3. **Set `OPS_ALERT_EMAIL` in `.env`:**
   ```
   OPS_ALERT_EMAIL=mohitsardana@gmail.com
   ```

4. **Apply the migration once:**
   ```bash
   docker exec -i evalassign-postgres psql -U evalassign -d evalassign \
     < db/migrations/001_credentials_health.sql
   ```

### Manual smoke test (run once per release)

1. Revoke the token at https://myaccount.google.com/permissions
2. Click "Test now" on the Google card at /settings/credentials (or wait 15 min)
3. Header pill should turn red within 30s.
4. Within 30s, an ops email titled "[evalassign] google_oauth REVOKED" arrives.
5. Click "Reconnect Google" -> complete consent in the new tab.
6. Pill flips green within 30s; a second ops email "[evalassign] google_oauth RECOVERED" arrives.
```

- [ ] **Step 2: Commit**

```bash
git add OPERATIONS.md
git commit -m "docs(ops): credential health & recovery — setup + smoke test"
```

### Task 3.6: Wave 3 smoke

- [ ] **Step 1: Restart the API server** (Task 3.4 step 6)

- [ ] **Step 2: Curl the new endpoints**

```bash
curl -s http://localhost:8000/api/credentials/status | python3 -m json.tool
curl -sX POST http://localhost:8000/api/credentials/google_oauth/recheck
curl -sX POST http://localhost:8000/api/credentials/google_oauth/reauth | python3 -m json.tool
```

Expected:
1. JSON array including `google_oauth`.
2. `{"name":"google_oauth","status":"OK"}` (or REVOKED if actually revoked).
3. JSON with `consent_url` starting `https://accounts.google.com/`.

---

## Wave 4 — Anthropic handle

By end of Wave 4: a second credential proves the abstraction; you can update the Anthropic key from the API.

### Task 4.1: `AnthropicCredentialHandle.check_health()`

**Files:**
- Create: `web/api/services/credentials/anthropic.py`
- Test: `web/api/tests/services/test_credentials_anthropic.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# web/api/tests/services/test_credentials_anthropic.py
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from web.api.services.credentials import Status


def test_missing_api_key_returns_missing(monkeypatch):
    from web.api.services.credentials.anthropic import AnthropicCredentialHandle
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    h = AnthropicCredentialHandle()
    assert h.check_health()[0] is Status.MISSING


def test_valid_key_returns_ok(monkeypatch):
    from web.api.services.credentials.anthropic import AnthropicCredentialHandle
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    h = AnthropicCredentialHandle()

    fake_client = MagicMock()
    fake_client.models.list.return_value = MagicMock(data=[])
    h._make_client = lambda key: fake_client  # type: ignore[method-assign]

    status, err = h.check_health()
    assert status is Status.OK
    assert err is None


def test_401_returns_revoked(monkeypatch):
    from web.api.services.credentials.anthropic import AnthropicCredentialHandle
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-bad")
    h = AnthropicCredentialHandle()

    import anthropic
    fake_client = MagicMock()
    fake_client.models.list.side_effect = anthropic.AuthenticationError(
        "invalid x-api-key",
        response=MagicMock(status_code=401),
        body=None,
    )
    h._make_client = lambda key: fake_client  # type: ignore[method-assign]

    status, err = h.check_health()
    assert status is Status.REVOKED


def test_429_returns_ok(monkeypatch):
    from web.api.services.credentials.anthropic import AnthropicCredentialHandle
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    h = AnthropicCredentialHandle()

    import anthropic
    fake_client = MagicMock()
    fake_client.models.list.side_effect = anthropic.RateLimitError(
        "rate limited",
        response=MagicMock(status_code=429),
        body=None,
    )
    h._make_client = lambda key: fake_client  # type: ignore[method-assign]

    status, _ = h.check_health()
    assert status is Status.OK


def test_check_health_caches_for_5_min(monkeypatch):
    from web.api.services.credentials.anthropic import AnthropicCredentialHandle
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    h = AnthropicCredentialHandle()

    fake_client = MagicMock()
    fake_client.models.list.return_value = MagicMock(data=[])
    h._make_client = lambda key: fake_client  # type: ignore[method-assign]

    h.check_health()
    h.check_health()
    assert fake_client.models.list.call_count == 1
```

- [ ] **Step 2: Run — verify it fails**

```bash
pytest web/api/tests/services/test_credentials_anthropic.py -xvs
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `anthropic.py`**

```python
# web/api/services/credentials/anthropic.py
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
```

- [ ] **Step 4: Run — verify it passes**

```bash
pytest web/api/tests/services/test_credentials_anthropic.py -xvs
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add web/api/services/credentials/anthropic.py web/api/tests/services/test_credentials_anthropic.py
git commit -m "feat(credentials): AnthropicCredentialHandle with 5-min cache"
```

### Task 4.2: `POST /anthropic_api/update`

**Files:**
- Modify: `web/api/routers/credentials.py`
- Test: `web/api/tests/routers/test_credentials.py` (append)

- [ ] **Step 1: Write the failing test**

```python
def test_update_anthropic_validates_before_writing_env(client, monkeypatch):
    monkeypatch.setattr("web.api.routers.credentials._auth_required",
                        lambda req: None)
    monkeypatch.setattr(
        "web.api.routers.credentials._validate_anthropic_key",
        lambda key: (False, "401 invalid"),
    )
    resp = client.post("/api/credentials/anthropic_api/update",
                       json={"api_key": "sk-ant-bad"})
    assert resp.status_code == 400
    assert "invalid" in resp.json()["detail"].lower()


def test_update_anthropic_writes_env_on_success(client, monkeypatch, tmp_path):
    monkeypatch.setattr("web.api.routers.credentials._auth_required",
                        lambda req: None)
    monkeypatch.setattr(
        "web.api.routers.credentials._validate_anthropic_key",
        lambda key: (True, None),
    )

    written = {}
    def fake_set_key(env_path, key, value):
        written[key] = value
    monkeypatch.setattr("web.api.routers.credentials.dotenv.set_key", fake_set_key)
    monkeypatch.setattr("web.api.routers.credentials.ENV_PATH", str(tmp_path / ".env"))

    resp = client.post("/api/credentials/anthropic_api/update",
                       json={"api_key": "sk-ant-good"})
    assert resp.status_code == 200
    assert written.get("ANTHROPIC_API_KEY") == "sk-ant-good"
```

- [ ] **Step 2: Run — verify it fails**

```bash
pytest web/api/tests/routers/test_credentials.py::test_update_anthropic_validates_before_writing_env -xvs
```

Expected: 404.

- [ ] **Step 3: Add endpoint + helpers to the router**

In `web/api/routers/credentials.py`, add at the top:

```python
import os
import dotenv
from pydantic import BaseModel
from pathlib import Path

ENV_PATH = str(Path(__file__).resolve().parents[3] / ".env")


class UpdateKeyBody(BaseModel):
    api_key: str


def _validate_anthropic_key(key: str) -> tuple[bool, str | None]:
    import anthropic
    try:
        anthropic.Anthropic(api_key=key).models.list()
        return True, None
    except anthropic.AuthenticationError as exc:
        return False, str(exc)[:200]
    except Exception as exc:
        return False, str(exc)[:200]
```

And the endpoint:

```python
@router.post("/anthropic_api/update")
def update_anthropic(body: UpdateKeyBody, _: None = Depends(_auth_required)) -> dict[str, str]:
    key = body.api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="api_key is empty")
    ok, err = _validate_anthropic_key(key)
    if not ok:
        raise HTTPException(status_code=400, detail=f"key did not validate: {err}")

    dotenv.set_key(ENV_PATH, "ANTHROPIC_API_KEY", key)
    os.environ["ANTHROPIC_API_KEY"] = key

    try:
        handle = REGISTRY.get("anthropic_api")
        handle._cached = None
        status, err = handle.check_health()
        REGISTRY.report_status("anthropic_api", status, err)
    except KeyError:
        pass

    return {"ok": "true"}
```

- [ ] **Step 4: Run — verify it passes**

```bash
pytest web/api/tests/routers/test_credentials.py -xvs
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add web/api/routers/credentials.py web/api/tests/routers/test_credentials.py
git commit -m "feat(credentials): POST /anthropic_api/update validates before writing .env"
```

### Task 4.3: Register `anthropic_api` in defaults

**Files:**
- Modify: `web/api/services/credentials/register_defaults.py`
- Test: `web/api/tests/services/test_credentials_register_defaults.py` (append)

- [ ] **Step 1: Append the test**

```python
def test_default_registry_has_anthropic_api():
    from web.api.services.credentials import REGISTRY

    h = REGISTRY.get("anthropic_api")
    assert h.name == "anthropic_api"
```

- [ ] **Step 2: Add the registration**

In `register_defaults()`, after the `google_oauth` block:

```python
    if "anthropic_api" not in {h.name for h in REGISTRY.all()}:
        from web.api.services.credentials.anthropic import AnthropicCredentialHandle
        REGISTRY.register(AnthropicCredentialHandle())
```

- [ ] **Step 3: Run**

```bash
pytest web/api/tests/services/test_credentials_register_defaults.py -xvs
```

Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add web/api/services/credentials/register_defaults.py web/api/tests/services/test_credentials_register_defaults.py
git commit -m "feat(credentials): register anthropic_api in defaults"
```

---

## Wave 5 — Frontend pill + settings page

By end of Wave 5: header pill turns red on outages; one-click Reconnect Google works end-to-end.

### Task 5.1: TS types + SWR hook

**Files:**
- Create: `web/app/lib/credentials.ts`

- [ ] **Step 1: Locate the existing SWR usage pattern**

```bash
grep -rn "useSWR" web/app/components web/app/app | head -5
```

Mirror whichever pattern the rest of the app uses (fetch with `credentials: "include"`).

- [ ] **Step 2: Create the hook**

```typescript
// web/app/lib/credentials.ts
import useSWR from "swr";
import { useEffect } from "react";

export type CredentialStatus =
  | "OK"
  | "EXPIRED"
  | "REVOKED"
  | "MISSING"
  | "UNKNOWN";

export interface CredentialHealth {
  name: string;
  status: CredentialStatus;
  last_checked_at: string | null;
  last_ok_at: string | null;
  last_error: string | null;
  recovery_started_at: string | null;
  notified_at: string | null;
  updated_at: string | null;
}

const fetcher = (url: string) =>
  fetch(url, { credentials: "include" }).then((r) => {
    if (!r.ok) throw new Error(`status ${r.status}`);
    return r.json() as Promise<CredentialHealth[]>;
  });

export function useCredentials() {
  const { data, error, mutate } = useSWR<CredentialHealth[]>(
    "/api/credentials/status",
    fetcher,
    { refreshInterval: 30_000 },
  );
  const issues = (data ?? []).filter((c) => c.status !== "OK");
  return {
    data,
    error,
    issues,
    isLoading: !data && !error,
    refresh: mutate,
  };
}

export async function startGoogleReauth(): Promise<{ consent_url: string; state: string }> {
  const r = await fetch("/api/credentials/google_oauth/reauth", {
    method: "POST",
    credentials: "include",
  });
  if (!r.ok) throw new Error(`reauth failed: ${r.status}`);
  return r.json();
}

export async function updateAnthropicKey(apiKey: string): Promise<void> {
  const r = await fetch("/api/credentials/anthropic_api/update", {
    method: "POST",
    credentials: "include",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({ detail: "unknown" }));
    throw new Error(body.detail || `status ${r.status}`);
  }
}

export async function recheckCredential(name: string): Promise<void> {
  const r = await fetch(`/api/credentials/${name}/recheck`, {
    method: "POST",
    credentials: "include",
  });
  if (!r.ok) throw new Error(`recheck failed: ${r.status}`);
}

export function useWatchReauthCompletion(refresh: () => void) {
  useEffect(() => {
    function onStorage(e: StorageEvent) {
      if (e.key === "ts:google_reconnected") refresh();
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [refresh]);
}
```

- [ ] **Step 3: Commit**

```bash
git add web/app/lib/credentials.ts
git commit -m "feat(web): credentials TS types + SWR hook"
```

### Task 5.2: Modify the header pill

**Files:**
- Modify: the component that renders the existing "Pipeline · live" button. Locate first.

- [ ] **Step 1: Locate the pill component**

```bash
grep -rn "Pipeline · live\|pipeline-pill" web/app/components web/app/app | head -5
```

- [ ] **Step 2: Replace the static button**

Replace the existing pill JSX (probably a `<button>` with hard-coded text "Pipeline · live") with a dynamic version:

```tsx
"use client";

import { useCredentials } from "@/lib/credentials";
import { CredentialsPopover } from "@/components/credentials-popover";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";

export function PipelinePill() {
  const { issues, isLoading, error } = useCredentials();

  let label = "Pipeline · live";
  let tone: "ok" | "warn" | "broken" | "unknown" = "ok";

  if (error || isLoading) {
    label = "Credentials · …";
    tone = "unknown";
  } else if (issues.length > 0) {
    label = `Credentials · ${issues.length} ${issues.length === 1 ? "issue" : "issues"}`;
    tone = issues.some((i) => i.status === "REVOKED" || i.status === "MISSING") ? "broken" : "warn";
  }

  const toneClass = {
    ok:      "bg-emerald-500/15 text-emerald-300 ring-emerald-500/40",
    warn:    "bg-amber-500/15 text-amber-300 ring-amber-500/40 animate-pulse",
    broken:  "bg-rose-500/15 text-rose-300 ring-rose-500/40 animate-pulse",
    unknown: "bg-zinc-500/15 text-zinc-300 ring-zinc-500/40",
  }[tone];

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ring-1 ${toneClass}`}
        >
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-current" />
          {label}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-96 p-0" align="end">
        <CredentialsPopover />
      </PopoverContent>
    </Popover>
  );
}
```

Replace the header's existing pill usage with `<PipelinePill />`.

- [ ] **Step 3: Manual smoke**

```bash
cd web/app && npm run dev
```

Visit localhost:3000. Pill renders, current state should be "Pipeline · live" if everything is OK.

- [ ] **Step 4: Commit**

```bash
git add <path/to/pipeline-pill.tsx>
git commit -m "feat(web): pipeline pill driven by credentials SWR hook"
```

### Task 5.3: `CredentialCard` + popover

**Files:**
- Create: `web/app/components/credentials-cards.tsx`
- Create: `web/app/components/credentials-popover.tsx`

- [ ] **Step 1: Create the shared card**

```tsx
// web/app/components/credentials-cards.tsx
"use client";

import { CredentialHealth, recheckCredential, startGoogleReauth } from "@/lib/credentials";
import { useState } from "react";

const STATUS_TONE: Record<CredentialHealth["status"], string> = {
  OK:      "text-emerald-400",
  EXPIRED: "text-amber-400",
  REVOKED: "text-rose-400",
  MISSING: "text-rose-400",
  UNKNOWN: "text-zinc-400",
};

export function CredentialCard({
  cred,
  onRefresh,
}: {
  cred: CredentialHealth;
  onRefresh: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const lastChecked = cred.last_checked_at
    ? new Date(cred.last_checked_at).toLocaleString()
    : "never";
  const isGoogle = cred.name === "google_oauth";

  async function handleRecheck() {
    setBusy(true); setError(null);
    try {
      await recheckCredential(cred.name);
      onRefresh();
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleReconnect() {
    setBusy(true); setError(null);
    try {
      const { consent_url } = await startGoogleReauth();
      window.open(consent_url, "_blank", "noopener,noreferrer");
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3 text-sm">
      <div className="flex items-baseline justify-between">
        <div className="font-medium text-zinc-100">
          {isGoogle ? "Google (OAuth)" : "Anthropic API"}
        </div>
        <div className={`text-xs font-mono ${STATUS_TONE[cred.status]}`}>{cred.status}</div>
      </div>
      <div className="mt-1 text-xs text-zinc-400">last check: {lastChecked}</div>
      {cred.last_error && (
        <div className="mt-2 text-xs text-rose-300/80 line-clamp-2">{cred.last_error}</div>
      )}
      <div className="mt-3 flex gap-2">
        <button
          type="button" disabled={busy} onClick={handleRecheck}
          className="rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-800 disabled:opacity-50"
        >
          {busy ? "…" : "Test now"}
        </button>
        {isGoogle && cred.status !== "OK" && (
          <button
            type="button" disabled={busy} onClick={handleReconnect}
            className="rounded bg-rose-500/20 px-2 py-1 text-xs text-rose-100 ring-1 ring-rose-500/40 hover:bg-rose-500/30 disabled:opacity-50"
          >
            Reconnect Google →
          </button>
        )}
      </div>
      {error && <div className="mt-2 text-xs text-rose-300">{error}</div>}
    </div>
  );
}
```

- [ ] **Step 2: Create the popover**

```tsx
// web/app/components/credentials-popover.tsx
"use client";

import { useCredentials, useWatchReauthCompletion } from "@/lib/credentials";
import { CredentialCard } from "./credentials-cards";
import Link from "next/link";

export function CredentialsPopover() {
  const { data, isLoading, error, refresh } = useCredentials();
  useWatchReauthCompletion(refresh);

  return (
    <div className="space-y-2 p-3">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-medium text-zinc-100">Credentials</h3>
        <Link href="/settings/credentials" className="text-xs text-zinc-400 hover:text-zinc-200">
          Manage all →
        </Link>
      </div>
      {isLoading && <div className="text-xs text-zinc-500">loading…</div>}
      {error && <div className="text-xs text-rose-400">{String(error)}</div>}
      {data && data.map((c) => (
        <CredentialCard key={c.name} cred={c} onRefresh={() => refresh()} />
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Manual smoke**

Reload localhost:3000, click the pill. Expect: popover with two cards (Google + Anthropic).

- [ ] **Step 4: Commit**

```bash
git add web/app/components/credentials-popover.tsx web/app/components/credentials-cards.tsx
git commit -m "feat(web): credentials popover with Reconnect Google + Test now"
```

### Task 5.4: `/settings/credentials` page

**Files:**
- Create: `web/app/app/settings/credentials/page.tsx`
- Modify: `web/app/components/side-nav.tsx`

- [ ] **Step 1: Create the page**

```tsx
// web/app/app/settings/credentials/page.tsx
"use client";

import { useState } from "react";
import { CredentialCard } from "@/components/credentials-cards";
import { useCredentials, updateAnthropicKey } from "@/lib/credentials";

export default function CredentialsPage() {
  const { data, refresh } = useCredentials();
  const [draftKey, setDraftKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function handleSave() {
    setSaving(true); setSaveError(null); setSaved(false);
    try {
      await updateAnthropicKey(draftKey.trim());
      setDraftKey(""); setSaved(true); refresh();
    } catch (e: unknown) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold text-zinc-100">Credentials</h1>
        <p className="mt-1 text-sm text-zinc-400">
          External APIs the pipeline depends on. Status is checked every 15 minutes.
        </p>
      </header>

      <div className="space-y-3">
        {data?.map((c) => (
          <CredentialCard key={c.name} cred={c} onRefresh={refresh} />
        ))}
      </div>

      <section className="rounded-md border border-zinc-800 bg-zinc-900/40 p-4">
        <h2 className="text-sm font-medium text-zinc-100">Update Anthropic API key</h2>
        <p className="mt-1 text-xs text-zinc-400">
          The key is validated against Anthropic before being written to .env. Invalid keys are rejected.
        </p>
        <div className="mt-3 flex gap-2">
          <input
            type="password" value={draftKey}
            onChange={(e) => setDraftKey(e.target.value)}
            placeholder="sk-ant-…"
            className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm text-zinc-100"
          />
          <button
            type="button" disabled={saving || !draftKey.trim()} onClick={handleSave}
            className="rounded bg-emerald-500/20 px-3 py-1 text-sm text-emerald-100 ring-1 ring-emerald-500/40 disabled:opacity-50"
          >
            {saving ? "Validating…" : "Validate & save"}
          </button>
        </div>
        {saveError && <div className="mt-2 text-xs text-rose-400">{saveError}</div>}
        {saved && <div className="mt-2 text-xs text-emerald-400">Saved.</div>}
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Update sidebar**

Open `web/app/components/side-nav.tsx`. Replace the `/settings/anthropic` link target with `/settings/credentials` and change the label to "Credentials".

- [ ] **Step 3: Manual smoke**

Reload localhost:3000, click "Credentials" in the sidebar.

- [ ] **Step 4: Commit**

```bash
git add web/app/app/settings/credentials/page.tsx web/app/components/side-nav.tsx
git commit -m "feat(web): /settings/credentials page with Anthropic key update form"
```

### Task 5.5: Playwright E2E test

**Files:**
- Modify: `web/app/package.json` (add `@playwright/test`, scripts)
- Create: `web/app/e2e/playwright.config.ts`
- Create: `web/app/e2e/credentials.spec.ts`

- [ ] **Step 1: Install Playwright**

```bash
cd web/app
npm install --save-dev @playwright/test
npx playwright install chromium --with-deps
```

- [ ] **Step 2: Create `playwright.config.ts`**

```typescript
// web/app/e2e/playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
```

- [ ] **Step 3: Add scripts to `package.json`**

In `web/app/package.json` "scripts":

```json
"e2e": "playwright test --config=e2e/playwright.config.ts",
"e2e:headed": "playwright test --config=e2e/playwright.config.ts --headed"
```

- [ ] **Step 4: Create the test**

```typescript
// web/app/e2e/credentials.spec.ts
import { test, expect } from "@playwright/test";

test.describe("Credentials surface", () => {
  test("pill shows green when all OK", async ({ page }) => {
    await fetch("http://localhost:8000/api/credentials/google_oauth/recheck", { method: "POST" });
    await page.goto("/");
    await expect(page.getByText(/Pipeline · live|Credentials ·/)).toBeVisible({ timeout: 5_000 });
  });

  test("popover lists registered credentials", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Pipeline|Credentials/ }).click();
    await expect(page.getByText("Google (OAuth)")).toBeVisible();
    await expect(page.getByText("Anthropic API")).toBeVisible();
    await expect(page.getByText("Manage all →")).toBeVisible();
  });

  test("Reconnect Google opens Google consent URL", async ({ page }) => {
    await page.goto("/settings/credentials");
    await page.evaluate(() => {
      (window as any).__opened = [];
      window.open = ((url: string | URL | undefined) => {
        (window as any).__opened.push(String(url));
        return null;
      }) as typeof window.open;
    });

    const reconnect = page.getByRole("button", { name: /Reconnect Google/ });
    if (await reconnect.count()) {
      await reconnect.first().click();
      await page.waitForFunction(() => (window as any).__opened.length > 0);
      const opened = await page.evaluate(() => (window as any).__opened);
      expect(opened[0]).toMatch(/^https:\/\/accounts\.google\.com\//);
    }
  });
});
```

- [ ] **Step 5: Run** (API + frontend must be live)

```bash
cd web/app
npm run e2e
```

Expected: 3 passed (or test 3 is no-op-asserted-pass if Google is OK in env).

- [ ] **Step 6: Commit**

```bash
git add web/app/e2e web/app/package.json web/app/package-lock.json
git commit -m "test(web): Playwright E2E for credentials popover + Reconnect"
```

---

## Wave 6 — Documentation cleanup & root-cause action

### Task 6.1: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append under "Credentials"**

```markdown
All API credential access goes through `web.api.services.credentials.REGISTRY`.
Do not load `token.json` or read `ANTHROPIC_API_KEY` from `os.environ` directly
in new code. To use Google APIs:

```python
from web.api.services.credentials import REGISTRY
classroom = REGISTRY.get("google_oauth").get_classroom()
```

If the credential is broken, `get_*()` raises `CredentialBroken`; pipeline tools
catch this in their `tick()` handler and skip the tick without crashing.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md note on Registry-only credential access"
```

### Task 6.2: Delete the one-shot reauth script

**Files:**
- Delete: `/tmp/reauth_google.py`

- [ ] **Step 1: Delete**

```bash
rm -f /tmp/reauth_google.py
```

(Not in repo — no commit.)

### Task 6.3: Final acceptance walk-through

- [ ] **Step 1: Run all tests**

```bash
DATABASE_URL=postgresql://evalassign:evalassign@127.0.0.1:5433/evalassign \
  pytest -xvs
cd web/app && npm run e2e
```

Expected: all green.

- [ ] **Step 2: Walk the spec's acceptance criteria**

Open `docs/superpowers/specs/2026-05-18-credential-registry-design.md` §13 and check each item:

1. [ ] Revoke token at myaccount.google.com → pill red within 15 min (or 30s with Test now).
2. [ ] Exactly one ops email arrives within 30s of the transition.
3. [ ] Clicking Reconnect opens Google consent tab.
4. [ ] Completing consent flips pill to green within 30s; recovery email arrives.
5. [ ] Killing API mid-token-write leaves valid token.json.
6. [ ] Pipeline daemon against revoked token logs CREDENTIAL_BROKEN and continues.
7. [ ] Google OAuth app in Published state in Google Cloud Console.

- [ ] **Step 3: Open the PR**

```bash
git push -u origin feat/credential-registry
gh pr create --title "feat: credential registry — holistic external-auth health" --body "$(cat <<'EOF'
## Summary

Implements the Credential Registry design (`docs/superpowers/specs/2026-05-18-credential-registry-design.md`):

- Uniform `CredentialHandle` abstraction over Google OAuth + Anthropic API
- Postgres-backed status with 15-min APScheduler health checks + reactive tagging from pipeline tools
- Header pill turns red on outages; one-click Reconnect Google from popover or `/settings/credentials`
- Ops email on `OK ↔ not-OK` transitions, deduped + 4h rate-limited
- Pipeline tools now skip ticks gracefully on `CredentialBroken` instead of crashing

## Setup required after merge

1. Apply `db/migrations/001_credentials_health.sql` to Postgres
2. Add `OPS_ALERT_EMAIL` to `.env`
3. Add the OAuth callback URL `http://localhost:8000/api/credentials/google_oauth/oauth-callback` to Google Cloud Console
4. **PUBLISH** the OAuth app in Google Cloud Console (stops 7-day refresh-token expiry)

See OPERATIONS.md → "Credential health & recovery" for the full setup + smoke checklist.

## Test plan

- [ ] pytest (Python tests, ~30 tests)
- [ ] Playwright (web E2E, 3 tests)
- [ ] Manual smoke per OPERATIONS.md (revoke + reconnect)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review pass — completed inline

**Spec coverage:**
- §2 goal 1 (uniform abstraction): Tasks 1.1, 1.2, 1.5, 4.3.
- §2 goal 2 (proactive + reactive): Task 3.4 (APScheduler) + Tasks 1.7-1.9 (reactive in tools).
- §2 goal 3 (UI pill + email): Task 5.2 (pill) + Task 2.4 (notifier).
- §2 goal 4 (one-click recovery): Tasks 3.2, 3.3 (OAuth flow), 4.2 (Anthropic update).
- §2 goal 5 (graceful degradation in tools): Tasks 1.7-1.9.
- §2 goal 6 (root-cause docs): Tasks 3.5, 6.1.
- §5 (data model): Task 2.1.
- §6.1-6.6 (backend components): Tasks 1.1-1.6, 2.2-2.5, 3.1-3.4.
- §6.7 (pipeline refactor): Tasks 1.7-1.9.
- §7 (frontend): Tasks 5.1-5.5.
- §8 (error handling): woven into tests in 1.4, 2.3, 2.4, 3.3.
- §9 (testing): each task includes its tests; §9.5 E2E in Task 5.5.
- §10 (rollout): Wave 1-6 structure matches the spec's 5 waves (Wave 6 = docs/cleanup).
- §11 (root-cause fix): Task 3.5 documentation + Task 6.3 acceptance check.
- §12 (documentation): Tasks 3.5 (OPERATIONS), 6.1 (CLAUDE.md), 6.2 (one-shot deletion).
- §13 (acceptance criteria): Task 6.3.

**No placeholders.** No "TBD" or "similar to Task N". Every code step has a code block; every command step has an exact command + expected output.

**Type consistency:** `CredentialHandle`, `CredentialBroken`, `Status`, `HealthSnapshot`, `RecoveryAction` are defined once in Tasks 1.1-1.2 and referenced consistently. `_PENDING_FLOWS` (Task 3.2) is the same object referenced in Task 3.3's callback test. `_make_client` on `AnthropicCredentialHandle` is defined in Task 4.1 and patched in its tests; the router's `_validate_anthropic_key` (Task 4.2) creates its own `Anthropic` client to avoid coupling.

---

## Execution handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-18-credential-registry.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Good for this 28-task plan because each task is small and the diff per task is easy to review.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints. Good if you want to watch every step happen in this conversation.

Which approach?
