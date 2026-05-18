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
