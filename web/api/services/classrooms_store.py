"""Read-through Postgres cache for the Google Classroom course list.

Decouples the queue-page classroom dropdown from /api/queue latency. The
queue endpoint does N+M Google API round trips (courseworks + submission
counts per course). The dropdown only needs course_id + label, so we
serve that from a thin cache with a 5-minute TTL.

Refresh strategy: read-through. If the most-recent row is older than
TTL, fetch fresh via classroom.courses().list() and upsert. If Google
fails or no credentials are available, fall back to whatever is in
the cache (stale-if-error) so the dropdown still shows something.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from tools.db import execute, execute_many, fetch_all, fetch_one

log = logging.getLogger(__name__)

TTL_SECONDS = 5 * 60.0  # 5 minutes


def _label_for(name: str, section: str) -> str:
    name = (name or "").strip()
    section = (section or "").strip()
    if name and section:
        return f"{name} · {section}"
    return name or section


def _cache_age_seconds() -> float | None:
    """Returns age of the most recently refreshed row in seconds, or
    None if the cache is empty."""
    row = fetch_one(
        "SELECT EXTRACT(EPOCH FROM (now() - max(fetched_at))) AS age "
        "FROM classroom_courses"
    )
    if not row or row.get("age") is None:
        return None
    return float(row["age"])


def _read_all() -> list[dict]:
    rows = fetch_all(
        "SELECT course_id, name, section "
        "FROM classroom_courses "
        "ORDER BY lower(name), course_id"
    )
    return [
        {
            "course_id": r["course_id"],
            "name": r["name"],
            "section": r["section"],
            "label": _label_for(r["name"], r["section"]),
        }
        for r in rows
    ]


def _refresh_from_google(classroom: Any) -> list[dict]:
    """Page through classroom.courses().list() and upsert into Postgres.
    Returns the freshly-fetched list. Caller should hold the refresh lock.
    """
    page_token = None
    fetched: list[tuple[str, str, str]] = []
    while True:
        resp = (
            classroom.courses()
            .list(courseStates=["ACTIVE"], pageSize=200, pageToken=page_token)
            .execute()
        )
        for c in resp.get("courses") or []:
            cid = c.get("id")
            if not cid:
                continue
            fetched.append(
                (cid, c.get("name") or "", c.get("section") or "")
            )
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    if fetched:
        # ACTIVE courses can be archived in Classroom; a plain UPSERT
        # would leave stale rows around. The table is small (tens of
        # rows) so a full replace is fine.
        execute("DELETE FROM classroom_courses")
        execute_many(
            "INSERT INTO classroom_courses (course_id, name, section, fetched_at) "
            "VALUES (%s, %s, %s, now())",
            fetched,
        )
    return _read_all()


_LOCK = threading.Lock()
_LAST_REFRESH_ATTEMPT_TS: float = 0.0
_REFRESH_BACKOFF_S = 30.0  # don't hammer Google when it returns errors


def list_classrooms(classroom: Any | None) -> list[dict]:
    """Public entry point. Returns the cached course list, refreshing
    transparently when stale. Never raises — falls back to whatever is
    in the cache (or [] if cold and no credentials)."""
    global _LAST_REFRESH_ATTEMPT_TS

    age = _cache_age_seconds()
    fresh_enough = age is not None and age < TTL_SECONDS
    if fresh_enough:
        return _read_all()

    with _LOCK:
        # Re-check after acquiring lock — another thread may have
        # refreshed while we were waiting.
        age = _cache_age_seconds()
        if age is not None and age < TTL_SECONDS:
            return _read_all()

        now = time.time()
        if (
            now - _LAST_REFRESH_ATTEMPT_TS < _REFRESH_BACKOFF_S
            and age is not None
        ):
            return _read_all()

        if classroom is None:
            return _read_all()  # may be empty; cold start + no creds

        _LAST_REFRESH_ATTEMPT_TS = now
        try:
            return _refresh_from_google(classroom)
        except Exception as exc:  # noqa: BLE001
            log.warning("classroom.courses().list() refresh failed: %s", exc)
            return _read_all()  # stale-if-error
