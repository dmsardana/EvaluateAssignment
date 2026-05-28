"""
FastAPI entry point for the ThinkingSouls Evaluation Console.

Run:
    uvicorn web.api.main:app --reload --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web.api.routers import (
    classrooms,
    credentials,
    queue,
    reports,
    scores,
    settings,
    students,
    wire,
)
from web.api.services.credentials.scheduler import (
    run_one_tick,
    start_scheduler,
    stop_scheduler,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1) Immediate credential health check so the rest of the app sees fresh status.
    try:
        run_one_tick()
    except Exception:
        import logging
        logging.getLogger(__name__).exception("initial credential tick failed")

    # 2) Schedule recurring credential checks (every 15 minutes).
    start_scheduler()

    # 3) Reap zombie GENERATING entries left over from prior process death.
    #    A daemon thread holding GENERATING dies when uvicorn exits. The state
    #    entry on Drive is left dangling. Sweep on every boot so the UI doesn't
    #    show a forever-spinning drawer for a worker that no longer exists.
    try:
        from web.api.deps import get_drive, get_keys_folder_id
        from web.api.services.queue import reap_zombie_generations
        n = reap_zombie_generations(get_drive(), get_keys_folder_id())
        if n:
            print(f"[boot] reaped {n} zombie GENERATING entries", flush=True)
    except Exception as e:  # noqa: BLE001 — never break startup
        print(f"[boot] zombie reaper failed (non-fatal): {e}", flush=True)

    yield

    # Shutdown
    stop_scheduler()


app = FastAPI(
    title="ThinkingSouls Evaluation Console API",
    version="0.1.0",
    lifespan=lifespan,
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
app.include_router(classrooms.router)


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


@app.get("/api/distribution")
def distribution():
    """Weekly band distribution backing the workspace snapshot."""
    from web.api.deps import get_drive, get_reports_folder_id
    from web.api.services.queue import get_distribution
    return get_distribution(get_drive(), get_reports_folder_id())


@app.get("/api/stats")
def stats():
    """Top-of-console stats — awaiting keys, queued submissions, est. cost."""
    from web.api.deps import (
        get_classroom,
        get_course_ids,
        get_drive,
        get_keys_folder_id,
        get_reports_folder_id,
    )
    from web.api.services.queue import get_stats
    return get_stats(
        classroom=get_classroom(),
        drive=get_drive(),
        keys_folder_id=get_keys_folder_id(),
        reports_folder_id=get_reports_folder_id(),
        course_ids=get_course_ids(),
    )
