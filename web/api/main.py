"""
FastAPI entry point for the ThinkingSouls Evaluation Console.

Run:
    uvicorn web.api.main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web.api.routers import credentials, queue, reports, scores, settings, students, wire

app = FastAPI(
    title="ThinkingSouls Evaluation Console API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(queue.router)
app.include_router(wire.router)
app.include_router(settings.router)
app.include_router(students.router)
app.include_router(reports.router)
app.include_router(scores.router)
app.include_router(credentials.router)


@app.on_event("startup")
def _reap_zombies():
    """A daemon thread holding GENERATING dies when uvicorn exits. The state
    entry on Drive is left dangling. Sweep on every boot so the UI doesn't
    show a forever-spinning drawer for a worker that no longer exists."""
    try:
        from web.api.deps import get_drive, get_keys_folder_id
        from web.api.services.queue import reap_zombie_generations
        n = reap_zombie_generations(get_drive(), get_keys_folder_id())
        if n:
            print(f"[boot] reaped {n} zombie GENERATING entries", flush=True)
    except Exception as e:  # noqa: BLE001 — never break startup
        print(f"[boot] zombie reaper failed (non-fatal): {e}", flush=True)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/budget")
def budget():
    """Snapshot used by the drawer to gate bulk-evaluate based on remaining
    spend headroom. Recomputed on every call (scores.csv read)."""
    from web.api.deps import get_drive, get_reports_folder_id
    from web.api.services.queue import get_budget_snapshot
    return get_budget_snapshot(get_drive(), get_reports_folder_id())
