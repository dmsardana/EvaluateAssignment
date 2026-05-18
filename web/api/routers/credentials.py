"""HTTP surface for the Credential Registry."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from web.api.services.credentials import REGISTRY, Status
from web.api.services.credentials import store
from web.api.services.credentials import google as google_module

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
