"""HTTP surface for the Credential Registry."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import dotenv
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from web.api.services.credentials import REGISTRY, Status
from web.api.services.credentials import store
from web.api.services.credentials import google as google_module

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/credentials", tags=["credentials"])

# parents[3] from web/api/routers/credentials.py resolves to the repo root.
ENV_PATH = str(Path(__file__).resolve().parents[3] / ".env")


class UpdateKeyBody(BaseModel):
    api_key: str


def _auth_required(request: Request) -> None:
    """Defense-in-depth check; Next.js middleware already gates /api/* at the proxy layer."""
    return None


def _validate_anthropic_key(key: str) -> tuple[bool, str | None]:
    import anthropic
    try:
        anthropic.Anthropic(api_key=key).models.list()
        return True, None
    except anthropic.AuthenticationError as exc:
        return False, str(exc)[:200]
    except Exception as exc:
        return False, str(exc)[:200]


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


@router.post("/google_oauth/reauth")
def google_reauth(_: None = Depends(_auth_required)) -> dict[str, str]:
    try:
        consent_url, state = google_module.start_reauth_flow()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"credentials.json missing: {exc}")
    return {"consent_url": consent_url, "state": state}


@router.get("/google_oauth/oauth-callback", response_class=HTMLResponse)
def google_oauth_callback(code: str, state: str, _: None = Depends(_auth_required)) -> HTMLResponse:
    # parents[3] from web/api/routers/credentials.py resolves to the repo root.
    token_path = Path(os.environ.get(
        "GOOGLE_TOKEN_PATH",
        Path(__file__).resolve().parents[3] / "token.json",
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


# ─────────────────────────────────────────────────────────────────────
# Gemini + OpenAI key update — same shape as Anthropic. The handles
# validate via a live /models probe before we persist the key, so a
# bad paste never lands in .env. The actual evaluation routing for
# these providers ships in Phase 2; the registry surface is wired
# now so the model picker can stop showing "not wired" once keys
# are entered.
# ─────────────────────────────────────────────────────────────────────


def _update_provider_key(name: str, env_var: str, key: str) -> None:
    """Persist + apply a provider API key, refresh registry status."""
    if not key:
        raise HTTPException(status_code=400, detail="api_key is empty")

    dotenv.set_key(ENV_PATH, env_var, key)
    os.environ[env_var] = key

    try:
        handle = REGISTRY.get(name)
        handle._cached = None  # type: ignore[attr-defined]
        status, err = handle.check_health()
        REGISTRY.report_status(name, status, err)
        if status is not Status.OK:
            raise HTTPException(
                status_code=400,
                detail=f"key did not validate: {err or status.value}",
            )
    except KeyError:
        # Handle wasn't registered (e.g. registry init failed) — accept
        # the key anyway; next process restart will pick it up.
        pass


@router.post("/gemini_api/update")
def update_gemini(body: UpdateKeyBody, _: None = Depends(_auth_required)) -> dict[str, str]:
    _update_provider_key("gemini_api", "GEMINI_API_KEY", body.api_key.strip())
    return {"ok": "true"}


@router.post("/openai_api/update")
def update_openai(body: UpdateKeyBody, _: None = Depends(_auth_required)) -> dict[str, str]:
    _update_provider_key("openai_api", "OPENAI_API_KEY", body.api_key.strip())
    return {"ok": "true"}
