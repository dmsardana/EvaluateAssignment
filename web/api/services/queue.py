"""
Service layer behind the Approval Queue / Drawer.

This module orchestrates everything the queue and drawer routes expose:
listing courseworks, generation lifecycle, per-question status, manual
AK uploads, evaluation jobs (with per-student progress), linking
graded PDFs back to students, and the bulk variants. It leans heavily
on existing tools under ``tools/`` for the actual side-effects
(Classroom + Drive + Anthropic + Gmail).

KEY FIX — see the legacy "evaluate() got an unexpected keyword argument
'model'" bug: ``evaluate_one_submission`` accepts ``model`` for API
compatibility but does NOT forward it to ``tools.evaluate_pdf.evaluate``
(which uses ``pick_model(meta["assignment_type"])`` internally).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable

from tools import db  # noqa: F401  (kept for future Postgres reads of profiles etc.)
from tools.review_state import load_state, save_state
from tools.track_scores import load_csv as _scores_load_csv
from tools.track_scores import save_csv as _scores_save_csv
from tools.watch_classroom import parse_assignment_meta
from tools.tier_config import KNOWN_TIERS, TIER_CONFIG, get_pass_pct


# ───── locally-defined link/unlink helpers ─────
#
# The original codebase exposed `is_linked`, `mark_linked`, `mark_unlinked`,
# `mark_linked_many`, `mark_unlinked_many` from `tools.track_scores`. The
# source `tools/track_scores.py` on disk only has the CSV layer — these
# helpers never got committed. Define minimal equivalents here that
# operate on the same `scores.csv` rows so link/unlink continues to work
# without an out-of-band Postgres migration.

_SCORES_LOCK = threading.Lock()


def is_linked(row: dict) -> bool:
    if not row:
        return False
    linked_at = (row.get("linked_at") or "").strip() if isinstance(row.get("linked_at"), str) else row.get("linked_at")
    unlinked_at = (row.get("unlinked_at") or "").strip() if isinstance(row.get("unlinked_at"), str) else row.get("unlinked_at")
    return bool(linked_at) and not bool(unlinked_at)


def _update_scores_row(
    drive,
    reports_folder_id: str,
    *,
    student_id: str,
    assignment_type: str,
    assignment_code: str,
    patch: dict,
) -> None:
    """Locate the matching row in scores.csv and apply ``patch`` in place."""
    if not reports_folder_id:
        return
    with _SCORES_LOCK:
        file_id, rows = _scores_load_csv(drive, reports_folder_id)
        changed = False
        for r in rows:
            if (
                r.get("student_id") == student_id
                and r.get("assignment_type") == assignment_type
                and r.get("assignment_code") == assignment_code
            ):
                r.update({k: ("" if v is None else str(v)) for k, v in patch.items()})
                changed = True
        if changed:
            _scores_save_csv(drive, reports_folder_id, file_id, rows)


def mark_linked(
    drive=None,
    reports_folder_id: str | None = None,
    *,
    student_id: str,
    assignment_type: str,
    assignment_code: str,
    shared_with_email: str,
    drive_permission_id: str,
    linked_at: str,
) -> None:
    if drive is None or not reports_folder_id:
        log.warning("mark_linked: no drive/reports_folder_id — skipped CSV update")
        return
    _update_scores_row(
        drive,
        reports_folder_id,
        student_id=student_id,
        assignment_type=assignment_type,
        assignment_code=assignment_code,
        patch={
            "shared_with_email": shared_with_email,
            "drive_permission_id": drive_permission_id,
            "linked_at": linked_at,
            "unlinked_at": "",
        },
    )


def mark_unlinked(
    drive=None,
    reports_folder_id: str | None = None,
    *,
    student_id: str,
    assignment_type: str,
    assignment_code: str,
    unlinked_at: str,
) -> None:
    if drive is None or not reports_folder_id:
        log.warning("mark_unlinked: no drive/reports_folder_id — skipped CSV update")
        return
    _update_scores_row(
        drive,
        reports_folder_id,
        student_id=student_id,
        assignment_type=assignment_type,
        assignment_code=assignment_code,
        patch={"unlinked_at": unlinked_at},
    )


def mark_linked_many(drive, reports_folder_id, rows: list[dict]) -> None:
    for r in rows:
        mark_linked(drive, reports_folder_id, **r)


def mark_unlinked_many(drive, reports_folder_id, rows: list[dict]) -> None:
    for r in rows:
        mark_unlinked(drive, reports_folder_id, **r)

log = logging.getLogger(__name__)


# ═════════════════════════ constants ═════════════════════════

COST_PER_KEY_USD = 0.50
COST_PER_GRADING_USD = 0.50

_CACHE_TTL_S = 30  # seconds


# ═════════════════════════ cache ═════════════════════════

_cache: dict[str, tuple[float, object]] = {}
_cache_lock = threading.Lock()


def _cache_get(key: str) -> object | None:
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts > _CACHE_TTL_S:
            _cache.pop(key, None)
            return None
        return value


def _cache_set(key: str, value: object) -> None:
    with _cache_lock:
        _cache[key] = (time.time(), value)


def invalidate_queue_cache() -> None:
    with _cache_lock:
        _cache.clear()


# ═════════════════════════ generation state ═════════════════════════

_GENERATION_PROGRESS: dict[str, dict] = {}
_CANCEL_FLAGS: dict[str, bool] = {}
_progress_lock = threading.Lock()


class GenerationCancelled(Exception):
    """Raised inside :func:`run_generation_inline` when the operator
    cancelled via :func:`abort_generation` mid-run."""


_STAGES: list[tuple[str, str]] = [
    ("fetching_pdf", "Fetching question paper"),
    ("calling_claude", "Generating answer key"),
    ("rendering_latex", "Rendering LaTeX"),
    ("uploading", "Uploading to Drive"),
    ("emailing", "Emailing for review"),
    ("done", "Done"),
]
_STAGE_INDEX = {name: idx for idx, (name, _label) in enumerate(_STAGES)}


def _record_progress(coursework_id: str, stage: str, label: str | None = None) -> None:
    if _CANCEL_FLAGS.get(coursework_id):
        raise GenerationCancelled(coursework_id)
    label = label or dict(_STAGES).get(stage, stage)
    idx = _STAGE_INDEX.get(stage, 0)
    pct = round(100 * (idx + 1) / max(1, len(_STAGES)))
    now = datetime.now(timezone.utc).isoformat()
    with _progress_lock:
        existing = _GENERATION_PROGRESS.get(coursework_id) or {}
        if "started_at" not in existing:
            existing["started_at"] = now
        existing.update(
            {
                "stage": stage,
                "label": label,
                "percent": pct,
                "updated_at": now,
            }
        )
        _GENERATION_PROGRESS[coursework_id] = existing
    print(
        f"[gen:{coursework_id}] {stage} ({pct}%) — {label}",
        flush=True,
    )


def get_generation_progress(coursework_id: str) -> dict | None:
    with _progress_lock:
        return dict(_GENERATION_PROGRESS.get(coursework_id) or {}) or None


# ═════════════════════════ queue listing ═════════════════════════

def _due_iso(cw: dict) -> str | None:
    due_date = cw.get("dueDate") or {}
    due_time = cw.get("dueTime") or {}
    if not due_date:
        return None
    y, m, d = due_date.get("year"), due_date.get("month"), due_date.get("day")
    if not (y and m and d):
        return None
    hh = due_time.get("hours") or 23
    mm = due_time.get("minutes") or 59
    try:
        return datetime(y, m, d, hh, mm, tzinfo=timezone.utc).isoformat()
    except Exception:
        return None


def _courseworks_for(classroom, course_id: str) -> list[dict]:
    out: list[dict] = []
    page_token = None
    while True:
        try:
            resp = (
                classroom.courses()
                .courseWork()
                .list(courseId=course_id, pageSize=100, pageToken=page_token)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("courseWork.list failed for %s: %s", course_id, exc)
            break
        for cw in resp.get("courseWork", []) or []:
            title = cw.get("title", "")
            asgn_type, asgn_code = parse_assignment_meta(title)
            if not asgn_type or not asgn_code:
                continue
            # Skip anything not declared in tier_config.TIER_CONFIG —
            # the Pydantic Tier literal and the frontend AssignmentType
            # are kept in lockstep with KNOWN_TIERS.
            if asgn_type not in KNOWN_TIERS:
                continue
            out.append(
                {
                    "coursework_id": cw["id"],
                    "course_id": course_id,
                    "assignment_type": asgn_type,
                    "assignment_code": asgn_code,
                    "assignment_title": title,
                    "created_at": cw.get("creationTime"),
                    "due_at": _due_iso(cw),
                    "alternate_link": cw.get("alternateLink"),
                    "work_type": cw.get("workType"),
                    "max_points": cw.get("maxPoints"),
                }
            )
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


def _list_courseworks(
    classroom_or_factory: Any,
    course_ids: list[str],
    classroom_factory: Callable[[], Any] | None = None,
) -> list[dict]:
    if not course_ids:
        return []

    # googleapiclient's discovery clients are NOT thread-safe. Parallel
    # calls across threads corrupt the underlying SSL connection state.
    # Only fan out when the caller supplied a factory that builds a fresh
    # client per worker thread; otherwise serialise.
    if classroom_factory is None:
        out: list[dict] = []
        for cid in course_ids:
            out.extend(_courseworks_for(classroom_or_factory, cid))
        return out

    tls = threading.local()

    def _client():
        existing = getattr(tls, "c", None)
        if existing is None:
            existing = classroom_factory()
            tls.c = existing
        return existing

    out = []
    with ThreadPoolExecutor(max_workers=min(len(course_ids), 4)) as ex:
        for cw_list in ex.map(
            lambda cid: _courseworks_for(_client(), cid), course_ids
        ):
            out.extend(cw_list)
    return out


def _count_submissions(classroom, course_id: str, coursework_id: str) -> int:
    try:
        resp = (
            classroom.courses()
            .courseWork()
            .studentSubmissions()
            .list(
                courseId=course_id,
                courseWorkId=coursework_id,
                states=["TURNED_IN", "RETURNED"],
                pageSize=200,
            )
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("studentSubmissions.list failed: %s", exc)
        return 0
    return len(resp.get("studentSubmissions", []) or [])


def _linked_rollup(scores_rows: list[dict]) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for r in scores_rows or []:
        if is_linked(r):
            out.add((r.get("assignment_type") or "", r.get("assignment_code") or ""))
    return out


def _maybe_reports_folder_id() -> str | None:
    val = (os.environ.get("GOOGLE_REPORTS_FOLDER_ID") or "").strip()
    return val or None


def list_queue(
    classroom,
    drive,
    keys_folder_id: str,
    course_ids: list[str],
    classroom_factory: Callable[[], Any] | None = None,
) -> list[dict]:
    cache_key = "queue:" + ",".join(course_ids or [])
    cached = _cache_get(cache_key)
    if isinstance(cached, list):
        return cached

    state = load_state(drive, keys_folder_id)
    cw_rows = _list_courseworks(classroom, course_ids, classroom_factory)
    scores_rows = _read_scores_csv(drive, _maybe_reports_folder_id())
    linked = _linked_rollup(scores_rows)

    # Submission counts. Parallel only when a thread-safe factory is supplied;
    # otherwise serialise to keep googleapiclient's discovery client happy.
    counts_by_id: dict[str, int] = {}
    if cw_rows:
        if classroom_factory is None:
            for row in cw_rows:
                counts_by_id[row["coursework_id"]] = _count_submissions(
                    classroom, row["course_id"], row["coursework_id"]
                )
        else:
            tls = threading.local()

            def _client():
                existing = getattr(tls, "c", None)
                if existing is None:
                    existing = classroom_factory()
                    tls.c = existing
                return existing

            with ThreadPoolExecutor(max_workers=min(len(cw_rows), 6)) as ex:
                results = list(
                    ex.map(
                        lambda row: (
                            row["coursework_id"],
                            _count_submissions(
                                _client(), row["course_id"], row["coursework_id"]
                            ),
                        ),
                        cw_rows,
                    )
                )
            counts_by_id = dict(results)

    items: list[dict] = []
    for row in cw_rows:
        entry = (state or {}).get(row["coursework_id"]) or {}
        status = entry.get("status") or "DETECTED"
        is_shared = (
            row["assignment_type"],
            row["assignment_code"],
        ) in linked and status == "APPROVED"
        if is_shared:
            status = "SHARED"
        items.append(
            {
                **row,
                "status": status,
                "submission_count": counts_by_id.get(row["coursework_id"], 0),
                "questions_count": entry.get("questions_count", 0)
                or len(entry.get("questions") or []),
                "flagged_count": sum(
                    1
                    for s in (entry.get("questions_status") or [])
                    if s == "needs_rework"
                ),
                "current_otp": entry.get("current_otp"),
                "model": entry.get("model"),
                "generated_at": entry.get("generated_at"),
                "approved_at": entry.get("approved_at"),
            }
        )

    items.sort(
        key=lambda r: (
            0 if r["status"] in ("PENDING_REVIEW", "NEEDS_REGEN") else 1,
            -(r.get("generated_at") or "").__hash__(),
        )
    )
    _cache_set(cache_key, items)
    return items


# ═════════════════════════ detail ═════════════════════════

def _drive_view_url(drive_id: str | None) -> str | None:
    if not drive_id:
        return None
    return f"https://drive.google.com/file/d/{drive_id}/view"


_SIZE_CACHE: dict[str, tuple[int | None, float]] = {}
_SIZE_CACHE_TTL = 24 * 3600.0


def _resolve_attachment_size(
    drive, drive_id: str | None, cwid: str | None, sid: str | None
) -> int | None:
    """File size in bytes for a Drive attachment, or None.

    Resolution order: local cached copy at web/api/_tmp/<cwid>/<sid>.pdf
    (free stat) → process-memoised Drive files().get(fields="size")
    with 24h TTL → None on any failure."""
    if not drive_id:
        return None
    if cwid and sid:
        local = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "_tmp", cwid, f"{sid}.pdf",
        )
        if os.path.exists(local):
            try:
                return os.path.getsize(local)
            except OSError:
                pass
    import time as _time
    now = _time.time()
    cached = _SIZE_CACHE.get(drive_id)
    if cached and now - cached[1] < _SIZE_CACHE_TTL:
        return cached[0]
    if drive is None:
        return None
    try:
        meta = drive.files().get(
            fileId=drive_id, fields="size", supportsAllDrives=True
        ).execute()
        size = int(meta.get("size") or 0) or None
    except Exception:
        size = None
    _SIZE_CACHE[drive_id] = (size, now)
    return size


def _format_material(m: dict) -> dict:
    if "driveFile" in m:
        d = m["driveFile"].get("driveFile") or m["driveFile"]
        drive_id = d.get("id")
        return {
            "kind": "drive_file",
            "title": d.get("title", ""),
            "url": d.get("alternateLink") or _drive_view_url(drive_id),
            "drive_id": drive_id,
            "thumbnail_url": d.get("thumbnailUrl"),
        }
    if "link" in m:
        link = m["link"]
        return {
            "kind": "link",
            "title": link.get("title", link.get("url", "link")),
            "url": link.get("url"),
            "drive_id": None,
            "thumbnail_url": link.get("thumbnailUrl"),
        }
    if "youtubeVideo" in m:
        y = m["youtubeVideo"]
        return {
            "kind": "youtube",
            "title": y.get("title", "video"),
            "url": y.get("alternateLink"),
            "drive_id": None,
            "thumbnail_url": y.get("thumbnailUrl"),
        }
    if "form" in m:
        f = m["form"]
        return {
            "kind": "form",
            "title": f.get("title", "form"),
            "url": f.get("formUrl"),
            "drive_id": None,
            "thumbnail_url": f.get("thumbnailUrl"),
        }
    return {"kind": "link", "title": "(unknown)", "url": None, "drive_id": None, "thumbnail_url": None}


def _roster(classroom, course_id: str) -> dict[str, str]:
    out: dict[str, str] = {}
    page_token = None
    while True:
        try:
            resp = (
                classroom.courses()
                .students()
                .list(courseId=course_id, pageSize=200, pageToken=page_token)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("roster fetch failed for %s: %s", course_id, exc)
            break
        for s in resp.get("students", []) or []:
            sid = s.get("userId")
            name = ((s.get("profile") or {}).get("name") or {}).get("fullName") or ""
            if sid:
                out[sid] = name.strip()
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


def get_detail(drive, keys_folder_id: str, coursework_id: str) -> dict | None:
    state = load_state(drive, keys_folder_id) or {}
    return state.get(coursework_id)


def find_in_queue_cache(coursework_id: str) -> dict | None:
    """Scan in-memory queue caches for a coursework_id match.

    Lets the detail endpoint resolve a brand-new assignment (e.g. a fresh
    GA on Classroom that hasn't yet gone through answer-key generation,
    so state.json has no entry for it). Returns the row from the cached
    queue listing — which already contains course_id, assignment_type,
    assignment_code, etc. — or None if no cache entry has it.
    """
    with _cache_lock:
        cache_snapshot = list(_cache.items())
    for key, entry in cache_snapshot:
        if not key.startswith("queue:"):
            continue
        ts, value = entry
        if time.time() - ts > _CACHE_TTL_S:
            continue
        if not isinstance(value, list):
            continue
        for row in value:
            if isinstance(row, dict) and row.get("coursework_id") == coursework_id:
                return row
    return None


def classroom_detail(classroom, course_id: str, coursework_id: str) -> dict:
    cache_key = f"cwdetail:{course_id}:{coursework_id}"
    cached = _cache_get(cache_key)
    if isinstance(cached, dict):
        return cached

    cw: dict = {}
    try:
        cw = (
            classroom.courses()
            .courseWork()
            .get(courseId=course_id, id=coursework_id)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("courseWork.get failed: %s", exc)
        return {}

    materials = [_format_material(m) for m in (cw.get("materials") or [])]
    due_at = _due_iso(cw)
    work_type = cw.get("workType")
    max_points: float | None = None
    try:
        if cw.get("maxPoints") is not None:
            max_points = float(cw["maxPoints"])
    except (TypeError, ValueError):
        max_points = None
    alternate_link = cw.get("alternateLink")
    description = cw.get("description") or ""

    submissions = []
    # Drive client for attachment size lookups; lazy + best-effort so a
    # credential blip doesn't break the whole detail view.
    drive = None
    try:
        from web.api.services.credentials import REGISTRY
        drive = REGISTRY.get("google_oauth").get_drive()
    except Exception as exc:  # noqa: BLE001
        log.warning("drive client unavailable for attachment-size lookup: %s", exc)

    try:
        roster = _roster(classroom, course_id)
        subs_resp = (
            classroom.courses()
            .courseWork()
            .studentSubmissions()
            .list(
                courseId=course_id,
                courseWorkId=coursework_id,
                states=["TURNED_IN", "RETURNED"],
                pageSize=200,
            )
            .execute()
        )
        for s in subs_resp.get("studentSubmissions", []) or []:
            sid = s.get("userId")
            attachments = []
            for att in (s.get("assignmentSubmission") or {}).get("attachments", []) or []:
                if "driveFile" in att:
                    df = att["driveFile"]
                    attachments.append(
                        {
                            "title": df.get("title", ""),
                            "url": df.get("alternateLink") or _drive_view_url(df.get("id")),
                            "drive_id": df.get("id"),
                            "size_bytes": _resolve_attachment_size(
                                drive, df.get("id"), coursework_id, sid
                            ),
                        }
                    )
                elif "link" in att:
                    attachments.append(
                        {
                            "title": att["link"].get("title", "link"),
                            "url": att["link"].get("url"),
                            "drive_id": None,
                            "size_bytes": None,
                        }
                    )
            submissions.append(
                {
                    "student_id": sid,
                    "student_name": roster.get(sid, ""),
                    "submission_id": s.get("id"),
                    "state": s.get("state", ""),
                    "submitted_at": (s.get("updateTime") or s.get("creationTime") or ""),
                    "late": bool(s.get("late")),
                    "attachments": attachments,
                    "alternate_link": s.get("alternateLink"),
                    "graded_percentage": None,
                    "graded_earned": None,
                    "graded_max": None,
                    "graded_at": None,
                    "report_drive_id": None,
                    "report_url": None,
                    "linked_at": None,
                    "unlinked_at": None,
                }
            )
    except Exception as exc:  # noqa: BLE001
        log.exception("submissions.list failed: %s", exc)

    out = {
        "materials": materials,
        "due_at": due_at,
        "alternate_link": alternate_link,
        "description": description,
        "work_type": work_type,
        "max_points": max_points,
        "submissions": submissions,
        "raw_submission_count": len(submissions),
    }
    _cache_set(cache_key, out)
    return out


# ═════════════════════════ generation ═════════════════════════

def start_generation(
    drive,
    keys_folder_id: str,
    coursework_id: str,
    summary: dict,
) -> None:
    state = load_state(drive, keys_folder_id) or {}
    entry = state.get(coursework_id) or {}
    entry.update(summary)
    entry.update(
        {
            "status": "GENERATING",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    state[coursework_id] = entry
    save_state(drive, keys_folder_id, state)
    with _progress_lock:
        _GENERATION_PROGRESS[coursework_id] = {
            "stage": "queued",
            "label": "Queued",
            "percent": 0,
            "started_at": entry["started_at"],
            "updated_at": entry["started_at"],
        }
    invalidate_queue_cache()


def run_generation_inline(
    course_id: str,
    coursework_id: str,
    asgn_type: str,
    asgn_code: str,
    asgn_title: str,
    keys_folder_id: str,
) -> None:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from tools.setup_drive import SCOPES
    from tools.generate_answer_key import process_coursework

    token_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "..",
        "..",
        "token.json",
    )
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    classroom = build("classroom", "v1", credentials=creds, cache_discovery=False)

    try:
        _record_progress(coursework_id, "fetching_pdf")
        state = load_state(drive, keys_folder_id) or {}
        new_entry = process_coursework(
            drive=drive,
            classroom=classroom,
            keys_folder_id=keys_folder_id,
            course_id=course_id,
            coursework_id=coursework_id,
            assignment_type=asgn_type,
            assignment_code=asgn_code,
            assignment_title=asgn_title,
            state=state,
            on_progress=lambda stage, label=None: _record_progress(
                coursework_id, stage, label
            ),
        )
        state[coursework_id] = new_entry
        save_state(drive, keys_folder_id, state)
        invalidate_queue_cache()
        _record_progress(coursework_id, "done")
    except GenerationCancelled:
        print(f"[gen:{coursework_id}] cancelled by operator", flush=True)
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("generation failed for %s: %s", coursework_id, exc)
        fail_generation(drive, keys_folder_id, coursework_id, str(exc))
        raise
    finally:
        with _progress_lock:
            _GENERATION_PROGRESS.pop(coursework_id, None)
        _CANCEL_FLAGS.pop(coursework_id, None)


def upload_manual_answer_key(
    drive,
    classroom,
    keys_folder_id: str,
    course_id: str,
    coursework_id: str,
    pdf_bytes: bytes,
    asgn_type: str,
    asgn_code: str,
    asgn_title: str,
) -> dict:
    from tools.generate_answer_key import upload_pdf_to_drive

    tmp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    pdf_path = os.path.join(tmp_dir, f"{asgn_type}_{asgn_code}.pdf")
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    drive_id = upload_pdf_to_drive(
        drive=drive,
        folder_id=keys_folder_id,
        local_path=pdf_path,
        assignment_type=asgn_type,
        assignment_code=asgn_code,
    )

    now = datetime.now(timezone.utc).isoformat()
    state = load_state(drive, keys_folder_id) or {}
    entry = state.get(coursework_id) or {}
    entry.update(
        {
            "course_id": course_id,
            "coursework_id": coursework_id,
            "assignment_type": asgn_type,
            "assignment_code": asgn_code,
            "assignment_title": asgn_title,
            "status": "APPROVED",
            "approved_at": now,
            "manual_upload": True,
            "drive_pdf_id": drive_id,
        }
    )
    state[coursework_id] = entry
    save_state(drive, keys_folder_id, state)
    _CANCEL_FLAGS.pop(coursework_id, None)
    invalidate_queue_cache()
    return entry


def approve(drive, keys_folder_id: str, classroom, coursework_id: str) -> dict:
    state = load_state(drive, keys_folder_id) or {}
    entry = state.get(coursework_id)
    if entry is None:
        raise KeyError(f"coursework {coursework_id} not found in state")
    now = datetime.now(timezone.utc).isoformat()
    entry["status"] = "APPROVED"
    entry["approved_at"] = now
    state[coursework_id] = entry
    save_state(drive, keys_folder_id, state)

    teacher_email = (os.environ.get("TEACHER_EMAIL") or "").strip()
    if teacher_email:
        try:
            qp_url = _question_paper_url(classroom, entry.get("course_id", ""), coursework_id)
            _send_approval_email(entry, qp_url, teacher_email)
        except Exception as exc:  # noqa: BLE001
            print(
                f"[approve:{coursework_id}] approval email failed (non-fatal): {exc}",
                flush=True,
            )

    invalidate_queue_cache()
    return entry


def _question_paper_url(classroom, course_id: str, coursework_id: str) -> str | None:
    try:
        cw = (
            classroom.courses()
            .courseWork()
            .get(courseId=course_id, id=coursework_id)
            .execute()
        )
    except Exception:
        return None
    for m in cw.get("materials") or []:
        fm = _format_material(m)
        if fm.get("url"):
            return fm["url"]
    return None


def _send_approval_email(entry: dict, qp_url: str | None, teacher_email: str) -> None:
    from tools.email_helper import send_simple_email

    subject = (
        f"AK approved — {entry.get('assignment_type','?')} "
        f"{entry.get('assignment_code','?')}"
    )
    title = (entry.get("assignment_title") or "").rstrip()
    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    qp_line = f"\nQuestion paper: {qp_url}" if qp_url else ""
    body_text = (
        f"Approved at {when}.\n"
        f"Title: {title}\n"
        f"Coursework ID: {entry.get('coursework_id','?')}{qp_line}\n"
    )
    body_html = (
        f"<p>Approved at <strong>{when}</strong>.</p>"
        f"<p>{title}</p>"
        f"<p>Coursework ID: <code>{entry.get('coursework_id','?')}</code></p>"
        + (f'<p><a href="{qp_url}">Question paper</a></p>' if qp_url else "")
    )
    send_simple_email(
        to_addr=teacher_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )


def set_question_status(
    drive,
    keys_folder_id: str,
    coursework_id: str,
    question_number: int,
    status: str,
) -> dict:
    if status not in ("pending", "approved", "needs_rework"):
        raise ValueError(f"invalid question status: {status}")
    state = load_state(drive, keys_folder_id) or {}
    entry = state.get(coursework_id)
    if entry is None:
        raise KeyError(coursework_id)
    qstatus = list(entry.get("questions_status") or [])
    n_questions = entry.get("questions_count") or len(entry.get("questions") or [])
    while len(qstatus) < n_questions:
        qstatus.append("pending")
    if question_number < 1 or question_number > len(qstatus):
        raise IndexError(f"question_number {question_number} out of range")
    qstatus[question_number - 1] = status
    entry["questions_status"] = qstatus
    entry["flagged_count"] = sum(1 for s in qstatus if s == "needs_rework")
    if status == "needs_rework" and entry.get("status") == "PENDING_REVIEW":
        entry["status"] = "NEEDS_REGEN"
    state[coursework_id] = entry
    save_state(drive, keys_folder_id, state)
    invalidate_queue_cache()
    return entry


def fail_generation(
    drive,
    keys_folder_id: str,
    coursework_id: str,
    error: str,
) -> None:
    state = load_state(drive, keys_folder_id) or {}
    entry = state.get(coursework_id) or {}
    entry["status"] = "DETECTED"
    errs = list(entry.get("errors") or [])
    errs.append(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "message": error[:5000],
        }
    )
    entry["errors"] = errs
    state[coursework_id] = entry
    save_state(drive, keys_folder_id, state)
    with _progress_lock:
        _GENERATION_PROGRESS.pop(coursework_id, None)
    _CANCEL_FLAGS.pop(coursework_id, None)
    invalidate_queue_cache()


def reap_zombie_generations(drive, keys_folder_id: str) -> int:
    state = load_state(drive, keys_folder_id) or {}
    reaped = 0
    for cwid, entry in list(state.items()):
        if (entry or {}).get("status") == "GENERATING":
            entry["status"] = "DETECTED"
            errs = list(entry.get("errors") or [])
            errs.append(
                {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "message": "worker died — auto-reaped on boot",
                }
            )
            entry["errors"] = errs
            state[cwid] = entry
            with _progress_lock:
                _GENERATION_PROGRESS.pop(cwid, None)
            _CANCEL_FLAGS.pop(cwid, None)
            reaped += 1
    if reaped:
        save_state(drive, keys_folder_id, state)
        invalidate_queue_cache()
    return reaped


def abort_generation(drive, keys_folder_id: str, coursework_id: str) -> None:
    _CANCEL_FLAGS[coursework_id] = True
    with _progress_lock:
        _GENERATION_PROGRESS.pop(coursework_id, None)
    state = load_state(drive, keys_folder_id) or {}
    entry = state.get(coursework_id)
    if entry is None:
        raise KeyError(coursework_id)
    entry["status"] = "DETECTED"
    state[coursework_id] = entry
    save_state(drive, keys_folder_id, state)
    invalidate_queue_cache()


def flag_for_reprocess(
    drive,
    keys_folder_id: str,
    coursework_id: str,
    flagged_question_numbers: list[int],
) -> dict:
    state = load_state(drive, keys_folder_id) or {}
    entry = state.get(coursework_id)
    if entry is None:
        raise KeyError(coursework_id)
    qstatus = list(entry.get("questions_status") or [])
    n_questions = entry.get("questions_count") or len(entry.get("questions") or [])
    while len(qstatus) < n_questions:
        qstatus.append("pending")
    for idx, _ in enumerate(qstatus):
        if (idx + 1) in flagged_question_numbers:
            qstatus[idx] = "needs_rework"
    entry["questions_status"] = qstatus
    entry["flagged_count"] = sum(1 for s in qstatus if s == "needs_rework")
    entry["status"] = "NEEDS_REGEN"
    entry["regen_count"] = int(entry.get("regen_count") or 0) + 1
    state[coursework_id] = entry
    save_state(drive, keys_folder_id, state)
    invalidate_queue_cache()
    return entry


# ═════════════════════════ scores ═════════════════════════

def _read_scores_csv(drive, reports_folder_id: str | None) -> list[dict]:
    """Read graded scores rows from the Drive CSV (``scores.csv``)."""
    if not reports_folder_id or drive is None:
        return []
    try:
        _, rows = _scores_load_csv(drive, reports_folder_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("scores fetch failed: %s", exc)
        return []
    return list(rows or [])


def scores_for_assignment(
    drive,
    reports_folder_id: str | None,
    assignment_type: str,
    assignment_code: str,
) -> list[dict]:
    """Return scores rows belonging to a single (type, code) assignment.

    Used by the queue-detail endpoint to merge graded results into the
    raw Classroom submissions, so the per-student row in the drawer can
    show ``graded_percentage``, ``report_url``, ``linked_at``, etc.
    """
    atype = (assignment_type or "").strip()
    acode = (assignment_code or "").strip()
    if not atype or not acode:
        return []
    out: list[dict] = []
    for r in _read_scores_csv(drive, reports_folder_id):
        if (r.get("assignment_type") or "").strip() == atype and (
            r.get("assignment_code") or ""
        ).strip() == acode:
            out.append(r)
    return out


def _band_for(pct: float | int | None) -> str:
    try:
        p = int(pct) if pct is not None else 0
    except (TypeError, ValueError):
        return "F-GAPS"
    trail = int(os.environ.get("THRESHOLD_TRAILBLAZER", "75"))
    qual = int(os.environ.get("THRESHOLD_QUALIFIER", "60"))
    devp = int(os.environ.get("THRESHOLD_DEVELOPING", "40"))
    if p >= trail:
        return "TRBLZ"
    if p >= qual:
        return "QUALIF"
    if p >= devp:
        return "DEVLP"
    return "F-GAPS"


def _initials(full_name: str) -> str:
    parts = (full_name or "").strip().split()
    if not parts:
        return "??"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][:1] + parts[-1][:1]).upper()


_NAME_PATTERN = re.compile(r"[^A-Za-z]+")


def _camel_no_spaces(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name or "")
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    parts = _NAME_PATTERN.split(ascii_only)
    return "".join(p for p in parts if p)


def _index_reports(drive, reports_folder_id: str | None) -> dict[str, str]:
    if not reports_folder_id:
        return {}
    cache_key = f"reports_idx:{reports_folder_id}"
    cached = _cache_get(cache_key)
    if isinstance(cached, dict):
        return cached
    out: dict[str, str] = {}
    page_token = None
    try:
        while True:
            resp = (
                drive.files()
                .list(
                    q=f"'{reports_folder_id}' in parents and trashed=false and "
                    "mimeType='application/pdf'",
                    spaces="drive",
                    fields="files(id,name),nextPageToken",
                    pageSize=200,
                    pageToken=page_token,
                )
                .execute()
            )
            for f in resp.get("files", []) or []:
                out[(f["name"] or "").lower()] = f["id"]
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    except Exception as exc:  # noqa: BLE001
        log.warning("reports index list failed: %s", exc)
    _cache_set(cache_key, out)
    return out


def _match_report(index: dict[str, str], row: dict) -> tuple[str | None, str | None]:
    name = row.get("student_name") or ""
    code = row.get("assignment_code") or ""
    date = (row.get("evaluation_date") or "")[:10]
    camel = _camel_no_spaces(name)
    candidates = [
        f"{camel}_{code}_{date}_Report.pdf",
        f"{camel}_{code}_Report.pdf",
    ]
    for cand in candidates:
        drive_id = index.get(cand.lower())
        if drive_id:
            return drive_id, _drive_view_url(drive_id)
    return row.get("report_drive_id") or None, row.get("report_url") or None


# ═════════════════════════ wire / distribution / stats ═════════════════════════

def list_wire(
    drive,
    reports_folder_id: str | None,
    limit: int = 50,
) -> list[dict]:
    rows = _read_scores_csv(drive, reports_folder_id)
    rows.sort(key=lambda r: (r.get("evaluation_date") or ""), reverse=True)
    index = _index_reports(drive, reports_folder_id)
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for r in rows[: limit * 2]:
        key = (
            r.get("student_id") or "",
            r.get("assignment_type") or "",
            r.get("assignment_code") or "",
        )
        if key in seen:
            continue
        seen.add(key)
        try:
            pct = float(r.get("percentage") or 0.0)
        except (TypeError, ValueError):
            pct = 0.0
        drive_id, view_url = _match_report(index, r)
        band = _band_for(pct)
        qualifies = None
        cutoff = get_pass_pct(r.get("assignment_type") or "")
        if cutoff is not None and pct >= cutoff:
            cfg = TIER_CONFIG.get(r.get("assignment_type") or "")
            if isinstance(cfg, dict):
                qualifies = cfg.get("promotes_to")
        out.append(
            {
                "student_id": r.get("student_id") or "",
                "student_name": r.get("student_name") or "",
                "assignment_type": r.get("assignment_type") or "WA",
                "assignment_code": r.get("assignment_code") or "",
                "assignment_title": r.get("assignment_title") or "",
                "percentage": round(pct, 1),
                "band": band,
                "qualifies_for": qualifies,
                "report_url": view_url,
                "report_drive_id": drive_id,
            }
        )
        if len(out) >= limit:
            break
    return out


def get_distribution(drive, reports_folder_id: str | None) -> dict:
    rows = _read_scores_csv(drive, reports_folder_id)
    now = datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()
    counts = {"trailblazer": 0, "qualifier": 0, "developing": 0, "foundational_gaps": 0}
    for r in rows:
        try:
            pct = float(r.get("percentage") or 0.0)
        except (TypeError, ValueError):
            continue
        band = _band_for(pct)
        if band == "TRBLZ":
            counts["trailblazer"] += 1
        elif band == "QUALIF":
            counts["qualifier"] += 1
        elif band == "DEVLP":
            counts["developing"] += 1
        else:
            counts["foundational_gaps"] += 1
    total = sum(counts.values())
    return {
        **counts,
        "total": total,
        "week_label": f"W{week:02d}, {year}",
    }


def get_stats(
    classroom,
    drive,
    keys_folder_id: str,
    reports_folder_id: str | None,
    course_ids: list[str],
    classroom_factory: Callable[[], Any] | None = None,
) -> dict:
    queue = list_queue(classroom, drive, keys_folder_id, course_ids, classroom_factory)
    awaiting_keys = sum(1 for q in queue if q["status"] == "PENDING_REVIEW")
    queued_submissions = sum(
        q.get("submission_count", 0) for q in queue if q["status"] == "APPROVED"
    )
    est_cost = round(
        awaiting_keys * COST_PER_KEY_USD + queued_submissions * COST_PER_GRADING_USD,
        2,
    )
    return {
        "awaiting_keys": awaiting_keys,
        "submissions_queued": queued_submissions,
        "estimated_cost_usd": est_cost,
        "week_distribution": get_distribution(drive, reports_folder_id),
    }


# ═════════════════════════ budget ═════════════════════════

class BudgetExceeded(Exception):
    def __init__(self, msg: str, available: float, requested: float) -> None:
        super().__init__(msg)
        self.available = available
        self.requested = requested


def already_graded_for_assignment(
    drive,
    reports_folder_id: str | None,
    coursework_id: str | None,
    assignment_code: str,
    assignment_type: str,
) -> dict[str, dict]:
    rows = _read_scores_csv(drive, reports_folder_id)
    out: dict[str, dict] = {}
    for r in rows:
        try:
            if (
                r.get("assignment_type") == assignment_type
                and r.get("assignment_code") == assignment_code
            ):
                if r.get("percentage") is not None:
                    out[r.get("student_id") or ""] = r
        except (TypeError, ValueError):
            continue
    return out


def get_budget_snapshot(drive, reports_folder_id: str | None) -> dict:
    try:
        budget = float(os.environ.get("ANTHROPIC_BUDGET_USD") or "50")
    except ValueError:
        budget = 50.0
    rows = _read_scores_csv(drive, reports_folder_id)
    spent = round(len(rows) * COST_PER_GRADING_USD, 2)
    available = max(0.0, round(budget - spent, 2))
    return {
        "budget_usd": round(budget, 2),
        "spent_usd": spent,
        "available_usd": available,
        "cost_per_grading_usd": COST_PER_GRADING_USD,
    }


# ═════════════════════════ evaluation ═════════════════════════

_EVAL_PROGRESS: dict[tuple[str, str], dict] = {}
_EVAL_CANCEL: dict[tuple[str, str], bool] = {}
_eval_lock = threading.Lock()

_EVAL_STAGES: list[tuple[str, str, int]] = [
    ("queued", "Queued", 5),
    ("downloading", "Downloading PDF", 15),
    ("calling_claude", "Grading with Claude", 25),
    ("rendering_report", "Rendering report", 70),
    ("uploading", "Uploading report", 85),
    ("tracking", "Updating scores", 95),
    ("done", "Done", 100),
]
_EVAL_STAGE_INDEX = {name: idx for idx, (name, _l, _p) in enumerate(_EVAL_STAGES)}
_EVAL_STAGE_LABEL = {name: (label, pct) for (name, label, pct) in _EVAL_STAGES}


def _compute_duration_seconds(started_at: str | None, completed_at: str | None) -> int | None:
    if not (started_at and completed_at):
        return None
    try:
        s = datetime.fromisoformat(started_at)
        e = datetime.fromisoformat(completed_at)
        return max(0, int((e - s).total_seconds()))
    except Exception:
        return None


def _eval_record(
    cwid: str,
    sid: str,
    stage: str,
    *,
    status: str = "running",
    error: str | None = None,
    percentage: float | None = None,
    report_drive_id: str | None = None,
    report_url: str | None = None,
) -> None:
    if _EVAL_CANCEL.get((cwid, sid)):
        raise GenerationCancelled(f"{cwid}/{sid}")
    label, pct = _EVAL_STAGE_LABEL.get(stage, (stage, 0))
    now = datetime.now(timezone.utc).isoformat()
    with _eval_lock:
        entry = _EVAL_PROGRESS.get((cwid, sid)) or {
            "coursework_id": cwid,
            "student_id": sid,
            "started_at": now,
        }
        entry.update(
            {
                "stage": stage,
                "label": label,
                "percent": pct,
                "status": status,
                "updated_at": now,
            }
        )
        if status in ("done", "failed", "cancelled"):
            entry["completed_at"] = now
            entry["duration_seconds"] = _compute_duration_seconds(
                entry.get("started_at"), now
            )
        if error is not None:
            entry["error"] = error
        if percentage is not None:
            entry["percentage"] = percentage
        if report_drive_id is not None:
            entry["report_drive_id"] = report_drive_id
        if report_url is not None:
            entry["report_url"] = report_url
        _EVAL_PROGRESS[(cwid, sid)] = entry


def get_eval_progress(coursework_id: str) -> dict[str, dict]:
    with _eval_lock:
        return {
            sid: dict(entry)
            for (cwid, sid), entry in _EVAL_PROGRESS.items()
            if cwid == coursework_id
        }


def _eval_cache_path(coursework_id: str, student_id: str) -> str:
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "_eval_cache",
    )
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, f"{coursework_id}_{student_id}.json")


def _percent_from_cache(coursework_id: str, student_id: str) -> float | None:
    p = _eval_cache_path(coursework_id, student_id)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return float((data.get("aggregate") or {}).get("percentage"))
    except Exception:
        return None


def _grade_from_percentage(percentage: float | None, max_points: float | None) -> float | None:
    if percentage is None or max_points is None:
        return None
    try:
        return round(float(max_points) * (float(percentage) / 100.0), 2)
    except (TypeError, ValueError):
        return None


def abort_evaluations(coursework_id: str) -> None:
    with _eval_lock:
        for key in list(_EVAL_PROGRESS.keys()):
            if key[0] == coursework_id:
                _EVAL_CANCEL[key] = True


def _find_submission_drive_id(
    classroom, course_id: str, coursework_id: str, student_id: str
) -> tuple[str, str | None, str | None]:
    student_name = ""
    submission_id = None
    drive_file_id = None
    try:
        resp = (
            classroom.courses()
            .courseWork()
            .studentSubmissions()
            .list(
                courseId=course_id,
                courseWorkId=coursework_id,
                userId=student_id,
                pageSize=10,
            )
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("studentSubmissions.list failed: %s", exc)
        return student_name, submission_id, drive_file_id
    for s in resp.get("studentSubmissions", []) or []:
        submission_id = s.get("id")
        for att in (s.get("assignmentSubmission") or {}).get("attachments", []) or []:
            df = att.get("driveFile")
            if df and df.get("id"):
                drive_file_id = df["id"]
                break
        if drive_file_id:
            break
    try:
        student_name = _roster(classroom, course_id).get(student_id, "")
    except Exception:
        pass
    return student_name, submission_id, drive_file_id


def _student_name_from_submissions(classroom, course_id: str, student_id: str) -> str:
    try:
        return _roster(classroom, course_id).get(student_id, "")
    except Exception:
        return ""


def evaluate_one_submission(
    course_id: str,
    coursework_id: str,
    student_id: str,
    keys_folder_id: str,
    reports_folder_id: str,
    force_reeval: bool = False,
    model: str | None = None,
    provider: str | None = None,
) -> dict:
    """Grade one submission end-to-end.

    NOTE: ``model`` is accepted as a parameter so :class:`EvaluateRequest`
    can keep its current shape, but it is **deliberately not** forwarded
    to :func:`tools.evaluate_pdf.evaluate`, which takes only
    ``(submission_path, answer_key_path, meta)`` and selects the model
    internally via ``pick_model(meta['assignment_type'])``. Forwarding
    ``model`` is the bug that caused every evaluation to crash with
    "evaluate() got an unexpected keyword argument 'model'".
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from tools.setup_drive import SCOPES
    from tools.download_pdf import download_file, find_answer_key
    from tools.evaluate_pdf import evaluate as evaluate_pdf
    from tools.generate_report import generate as generate_report
    from tools.upload_report import upload as upload_report
    from tools.track_scores import track as track_score

    token_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "..",
        "..",
        "token.json",
    )
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    classroom = build("classroom", "v1", credentials=creds, cache_discovery=False)

    state = load_state(drive, keys_folder_id) or {}
    entry = state.get(coursework_id) or {}
    asgn_type = entry.get("assignment_type", "WA")
    asgn_code = entry.get("assignment_code", "")
    asgn_title = entry.get("assignment_title", f"{asgn_type} {asgn_code}")
    max_points = entry.get("max_points")

    # Clear any stale progress entry from a prior run so this evaluation
    # starts with a fresh started_at + no carried-over error. Without this,
    # re-eval clicks silently reuse the old "done" entry (with yesterday's
    # error text intact), confusing the UI and the operator.
    with _eval_lock:
        _EVAL_PROGRESS.pop((coursework_id, student_id), None)
        _EVAL_CANCEL.pop((coursework_id, student_id), None)

    _eval_record(coursework_id, student_id, "queued")

    student_name, _submission_id, drive_file_id = _find_submission_drive_id(
        classroom, course_id, coursework_id, student_id
    )
    if not drive_file_id:
        _eval_record(
            coursework_id,
            student_id,
            "calling_claude",
            status="failed",
            error="no submission PDF found for this student",
        )
        return {
            "student_id": student_id,
            "status": "failed",
            "error": "no submission PDF found",
        }

    tmp_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "_tmp",
        coursework_id,
    )
    os.makedirs(tmp_dir, exist_ok=True)
    submission_path = os.path.join(tmp_dir, f"{student_id}.pdf")

    # find_answer_key returns a Drive file id, not a local path. Download
    # it to a per-coursework cache file so we can pass a real path to the
    # worker.
    ak_drive_id = find_answer_key(drive, keys_folder_id, asgn_type, asgn_code)
    answer_key_path = os.path.join(tmp_dir, f"_AK_{asgn_type}_{asgn_code}.pdf")
    if not os.path.exists(answer_key_path):
        download_file(drive, ak_drive_id, answer_key_path)

    _eval_record(coursework_id, student_id, "downloading")
    download_file(drive, drive_file_id, submission_path)

    eval_cache = _eval_cache_path(coursework_id, student_id)
    evaluation: dict | None = None
    if not force_reeval and os.path.exists(eval_cache):
        try:
            with open(eval_cache, "r", encoding="utf-8") as f:
                evaluation = json.load(f)
        except Exception:
            evaluation = None

    if evaluation is None:
        _eval_record(coursework_id, student_id, "calling_claude")
        meta = {
            "student_name": student_name,
            "student_id": student_id,
            "assignment_type": asgn_type,
            "assignment_code": asgn_code,
            "assignment_title": asgn_title,
            "submission_path": submission_path,
            "answer_key_path": answer_key_path,
        }
        try:
            evaluation = evaluate_pdf(
                submission_path,
                answer_key_path,
                meta,
                provider=(provider or "anthropic"),
                model=model,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("evaluate_pdf failed: %s", exc)
            _eval_record(
                coursework_id,
                student_id,
                "calling_claude",
                status="failed",
                error=str(exc)[:200],
            )
            return {"student_id": student_id, "status": "failed", "error": str(exc)}
        try:
            with open(eval_cache, "w", encoding="utf-8") as f:
                json.dump(evaluation, f, ensure_ascii=False, indent=2)
        except Exception as exc:  # noqa: BLE001
            log.warning("eval cache write failed: %s", exc)

    _eval_record(coursework_id, student_id, "rendering_report")
    pdf_path = generate_report(evaluation)

    _eval_record(coursework_id, student_id, "uploading")
    drive_id = upload_report(pdf_path, reports_folder_id)

    _eval_record(coursework_id, student_id, "tracking")
    # Drive scores.csv is a legacy mirror — Postgres is primary. Bound this
    # write so a slow/rate-limited Drive cannot stall the job at 95% for
    # minutes on end (Mrinalini-class hang). Fail-soft: log + continue.
    import concurrent.futures as _cf
    try:
        with _cf.ThreadPoolExecutor(max_workers=1) as _ex:
            _ex.submit(track_score, evaluation, reports_folder_id).result(timeout=30)
    except _cf.TimeoutError:
        log.warning(
            "track_score timed out after 30s for %s/%s — Drive CSV mirror "
            "will catch up later; Postgres row is authoritative",
            coursework_id, student_id,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("track_score failed for %s/%s: %s", coursework_id, student_id, exc)

    # track_score(build_row) doesn't include the freshly-uploaded report
    # location (legacy shape kept for back-compat with older callers).
    # Patch it onto the row now so /api/queue/{id} can surface the View
    # Report icon and the share-link flow has a target.
    if drive_id:
        try:
            _update_scores_row(
                drive,
                reports_folder_id,
                student_id=student_id,
                assignment_type=asgn_type,
                assignment_code=asgn_code,
                patch={
                    "report_drive_id": drive_id,
                    "report_url": _drive_view_url(drive_id),
                    "coursework_id": coursework_id,
                },
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("scores row patch (report fields) failed: %s", exc)

    pct = float((evaluation.get("aggregate") or {}).get("percentage") or 0.0)
    _grade_from_percentage(pct, max_points)
    _eval_record(
        coursework_id,
        student_id,
        "done",
        status="done",
        percentage=pct,
        report_drive_id=drive_id,
        report_url=_drive_view_url(drive_id),
    )
    return {
        "student_id": student_id,
        "status": "done",
        "percentage": pct,
        "report_drive_id": drive_id,
    }


def start_evaluation_job(
    drive,
    reports_folder_id: str,
    course_id: str,
    coursework_id: str,
    student_ids: list[str],
    keys_folder_id: str,
    concurrency: int = 3,
    force_reeval: bool = False,
    model: str | None = None,
    provider: str | None = None,
) -> dict:
    n = len(student_ids)
    if n == 0:
        return {
            "job_started": False,
            "student_count": 0,
            "estimated_cost_usd": 0.0,
            "available_usd": get_budget_snapshot(drive, reports_folder_id)["available_usd"],
            "concurrency": 0,
            "cached_count": 0,
            "fresh_count": 0,
        }
    budget = get_budget_snapshot(drive, reports_folder_id)
    cached_count = 0
    fresh_count = 0
    for sid in student_ids:
        if not force_reeval and _percent_from_cache(coursework_id, sid) is not None:
            cached_count += 1
        else:
            fresh_count += 1
    estimated = round(fresh_count * COST_PER_GRADING_USD, 2)
    if estimated > budget["available_usd"]:
        raise BudgetExceeded(
            f"Estimated ${estimated:.2f} > available ${budget['available_usd']:.2f}",
            available=budget["available_usd"],
            requested=estimated,
        )
    concurrency = max(1, min(10, int(concurrency or 3)))

    for sid in student_ids:
        _EVAL_CANCEL.pop((coursework_id, sid), None)
        _eval_record(coursework_id, sid, "queued")

    def _worker(sid: str):
        try:
            evaluate_one_submission(
                course_id=course_id,
                coursework_id=coursework_id,
                student_id=sid,
                keys_folder_id=keys_folder_id,
                reports_folder_id=reports_folder_id,
                force_reeval=force_reeval,
                model=model,
                provider=provider,
            )
        except GenerationCancelled:
            _eval_record(coursework_id, sid, "queued", status="cancelled")
        except Exception as exc:  # noqa: BLE001
            log.exception("evaluation worker died: %s", exc)
            _eval_record(
                coursework_id, sid, "calling_claude",
                status="failed", error=str(exc)[:200],
            )

    def _runner():
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            for _ in ex.map(_worker, student_ids):
                pass

    threading.Thread(target=_runner, name=f"eval-{coursework_id}", daemon=True).start()
    return {
        "job_started": True,
        "student_count": n,
        "estimated_cost_usd": estimated,
        "available_usd": budget["available_usd"],
        "concurrency": concurrency,
        "cached_count": cached_count,
        "fresh_count": fresh_count,
    }


# ═════════════════════════ linking ═════════════════════════

def _gmail_service():
    from googleapiclient.discovery import build
    from web.api.deps import _creds
    return build("gmail", "v1", credentials=_creds(), cache_discovery=False)


def _lookup_share_state(
    drive,
    reports_folder_id: str | None,
    assignment_type: str,
    assignment_code: str,
    student_id: str,
    coursework_id: str | None,
) -> dict | None:
    rows = _read_scores_csv(drive, reports_folder_id)
    for r in rows:
        if (
            r.get("assignment_type") == assignment_type
            and r.get("assignment_code") == assignment_code
            and r.get("student_id") == student_id
        ):
            return r
    return None


def link_submission(
    classroom,
    drive,
    reports_folder_id: str,
    course_id: str,
    coursework_id: str,
    student_id: str,
    assignment_type: str,
    assignment_code: str,
    max_points: float | None = None,
    student_email_override: str | None = None,
) -> dict:
    from tools.return_to_classroom import link_report_to_submission
    from tools.student_profiles import lookup_email, save_profile

    row = _lookup_share_state(
        drive, reports_folder_id, assignment_type, assignment_code, student_id, coursework_id
    )
    if not row or not row.get("report_drive_id"):
        raise ValueError("no graded report on file for that student")

    student_name, submission_id, _ = _find_submission_drive_id(
        classroom, course_id, coursework_id, student_id
    )

    email = (student_email_override or "").strip() or lookup_email(
        drive, reports_folder_id, student_id
    )
    percentage: float | None
    try:
        percentage = float(row.get("percentage") or 0.0)
    except (TypeError, ValueError):
        percentage = None
    drive_view_url = _drive_view_url(row.get("report_drive_id")) or ""

    out = link_report_to_submission(
        classroom=classroom,
        drive=drive,
        gmail=_gmail_service(),
        course_id=course_id,
        coursework_id=coursework_id,
        submission_id=submission_id,
        drive_file_id=row["report_drive_id"],
        student_id=student_id,
        student_name=student_name or row.get("student_name", ""),
        assignment_title=row.get("assignment_title") or f"{assignment_type} {assignment_code}",
        percentage=percentage,
        drive_view_url=drive_view_url,
        student_email=email or None,
        assigned_grade=_grade_from_percentage(percentage, max_points),
    )
    mark_linked(
        drive,
        reports_folder_id,
        student_id=student_id,
        assignment_type=assignment_type,
        assignment_code=assignment_code,
        shared_with_email=out.get("shared_with_email", ""),
        drive_permission_id=out.get("drive_permission_id", ""),
        linked_at=out.get("linked_at", ""),
    )
    if email:
        try:
            save_profile(drive, reports_folder_id, student_id, email=email)
        except Exception as exc:  # noqa: BLE001
            log.warning("save_profile failed (non-fatal): %s", exc)
    invalidate_queue_cache()
    return out


def unlink_submission(
    classroom,
    drive,
    reports_folder_id: str,
    course_id: str,
    coursework_id: str,
    student_id: str,
    assignment_type: str,
    assignment_code: str,
) -> dict:
    from tools.return_to_classroom import unlink_report_from_submission

    row = _lookup_share_state(
        drive, reports_folder_id, assignment_type, assignment_code, student_id, coursework_id
    )
    if not row:
        raise ValueError("no share state for that student")
    _, submission_id, _ = _find_submission_drive_id(
        classroom, course_id, coursework_id, student_id
    )
    out = unlink_report_from_submission(
        classroom=classroom,
        drive=drive,
        course_id=course_id,
        coursework_id=coursework_id,
        submission_id=submission_id,
        drive_file_id=row.get("report_drive_id") or "",
        drive_permission_id=row.get("drive_permission_id"),
    )
    mark_unlinked(
        drive,
        reports_folder_id,
        student_id=student_id,
        assignment_type=assignment_type,
        assignment_code=assignment_code,
        unlinked_at=out.get("unlinked_at", ""),
    )
    invalidate_queue_cache()
    return out


def _eligible_for_bulk(
    drive,
    reports_folder_id: str | None,
    assignment_type: str,
    assignment_code: str,
    coursework_id: str | None,
    link_or_unlink: str,
) -> list[dict]:
    rows = _read_scores_csv(drive, reports_folder_id)
    out: list[dict] = []
    for r in rows:
        if r.get("assignment_type") != assignment_type:
            continue
        if r.get("assignment_code") != assignment_code:
            continue
        if link_or_unlink == "link" and is_linked(r):
            continue
        if link_or_unlink == "unlink" and not is_linked(r):
            continue
        out.append(r)
    return out


# ───── Bulk jobs ─────

_BULK_JOBS: dict[str, dict] = {}
_BULK_JOBS_LOCK = threading.Lock()


def _now_share_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_bulk_job(coursework_id: str) -> dict | None:
    with _BULK_JOBS_LOCK:
        return dict(_BULK_JOBS.get(coursework_id) or {}) or None


def _set_bulk_job(coursework_id: str, patch: dict) -> None:
    with _BULK_JOBS_LOCK:
        existing = _BULK_JOBS.get(coursework_id) or {}
        existing.update(patch)
        _BULK_JOBS[coursework_id] = existing


def _start_bulk_worker(
    coursework_id: str,
    kind: str,
    sids: list[str],
    worker: Callable[[], None],
) -> None:
    _set_bulk_job(
        coursework_id,
        {
            "kind": kind,
            "total": len(sids),
            "done": 0,
            "failed": 0,
            "started_at": _now_share_iso(),
            "status": "running",
        },
    )
    threading.Thread(
        target=worker, name=f"bulk-{kind}-{coursework_id}", daemon=True
    ).start()


def bulk_link_all_graded(
    classroom,
    drive,
    reports_folder_id: str,
    course_id: str,
    coursework_id: str,
    assignment_type: str,
    assignment_code: str,
    max_points: float | None = None,
) -> dict:
    if (get_bulk_job(coursework_id) or {}).get("status") == "running":
        return {"job_started": False, "reason": "bulk job already running"}
    eligible = _eligible_for_bulk(
        drive, reports_folder_id, assignment_type, assignment_code, coursework_id, "link"
    )
    sids = [r["student_id"] for r in eligible if r.get("student_id")]
    if not sids:
        _set_bulk_job(coursework_id, {"status": "done", "kind": "link", "total": 0, "done": 0, "failed": 0})
        return {"job_started": False, "reason": "no eligible submissions"}

    def _worker():
        done = 0
        failed = 0
        for sid in sids:
            try:
                link_submission(
                    classroom=classroom, drive=drive,
                    reports_folder_id=reports_folder_id,
                    course_id=course_id, coursework_id=coursework_id,
                    student_id=sid,
                    assignment_type=assignment_type, assignment_code=assignment_code,
                    max_points=max_points,
                )
                done += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("bulk link failed for %s: %s", sid, exc)
                failed += 1
            _set_bulk_job(coursework_id, {"done": done, "failed": failed})
        _set_bulk_job(coursework_id, {"status": "done"})

    _start_bulk_worker(coursework_id, "link", sids, _worker)
    return {"job_started": True, "total": len(sids)}


def bulk_unlink_all_linked(
    classroom,
    drive,
    reports_folder_id: str,
    course_id: str,
    coursework_id: str,
    assignment_type: str,
    assignment_code: str,
) -> dict:
    if (get_bulk_job(coursework_id) or {}).get("status") == "running":
        return {"job_started": False, "reason": "bulk job already running"}
    eligible = _eligible_for_bulk(
        drive, reports_folder_id, assignment_type, assignment_code, coursework_id, "unlink"
    )
    sids = [r["student_id"] for r in eligible if r.get("student_id")]
    if not sids:
        _set_bulk_job(coursework_id, {"status": "done", "kind": "unlink", "total": 0, "done": 0, "failed": 0})
        return {"job_started": False, "reason": "no linked submissions"}

    def _worker():
        done = 0
        failed = 0
        for sid in sids:
            try:
                unlink_submission(
                    classroom=classroom, drive=drive,
                    reports_folder_id=reports_folder_id,
                    course_id=course_id, coursework_id=coursework_id,
                    student_id=sid,
                    assignment_type=assignment_type, assignment_code=assignment_code,
                )
                done += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("bulk unlink failed for %s: %s", sid, exc)
                failed += 1
            _set_bulk_job(coursework_id, {"done": done, "failed": failed})
        _set_bulk_job(coursework_id, {"status": "done"})

    _start_bulk_worker(coursework_id, "unlink", sids, _worker)
    return {"job_started": True, "total": len(sids)}


# ═════════════════════════ students ═════════════════════════

def _course_meta(classroom, course_id: str) -> dict:
    try:
        c = classroom.courses().get(id=course_id).execute()
    except Exception:
        return {"course_id": course_id, "name": course_id}
    return {
        "course_id": course_id,
        "name": (c.get("name") or "").strip(),
        "section": (c.get("section") or "").strip(),
        "enrollment_code": (c.get("enrollmentCode") or "").strip(),
    }


def _course_label(meta: dict) -> str:
    section = meta.get("section")
    if section:
        return f"{meta.get('name','')} · {section}"
    return meta.get("name") or meta.get("course_id") or ""


def list_students_with_profiles(
    classroom,
    drive,
    reports_folder_id: str,
    course_ids: list[str],
    classroom_factory: Callable[[], Any] | None = None,
) -> list[dict]:
    from tools.student_profiles import load_profiles

    profiles = load_profiles(drive, reports_folder_id)
    tls = threading.local()

    def _client():
        if classroom_factory is None:
            return classroom
        existing = getattr(tls, "c", None)
        if existing is None:
            existing = classroom_factory()
            tls.c = existing
        return existing

    course_metas: dict[str, dict] = {}
    rosters: dict[str, dict[str, str]] = {}
    if course_ids:
        if classroom_factory is None:
            # Sequential — discovery client not thread-safe.
            for cid in course_ids:
                course_metas[cid] = _course_meta(classroom, cid)
                rosters[cid] = _roster(classroom, cid)
        else:
            with ThreadPoolExecutor(max_workers=min(len(course_ids), 4)) as ex:
                for cid, meta in zip(
                    course_ids,
                    ex.map(lambda c: _course_meta(_client(), c), course_ids),
                ):
                    course_metas[cid] = meta
                for cid, roster in zip(
                    course_ids,
                    ex.map(lambda c: _roster(_client(), c), course_ids),
                ):
                    rosters[cid] = roster

    enrolments: dict[str, list[str]] = {}
    names: dict[str, str] = {}
    for cid, roster in rosters.items():
        for sid, name in roster.items():
            enrolments.setdefault(sid, []).append(cid)
            names.setdefault(sid, name)

    out: list[dict] = []
    seen: set[str] = set()
    for sid, name in names.items():
        seen.add(sid)
        course_chips = []
        for cid in enrolments.get(sid, []):
            meta = course_metas.get(cid) or {"course_id": cid, "name": cid}
            course_chips.append(
                {
                    "course_id": meta["course_id"],
                    "name": meta.get("name") or "",
                    "section": meta.get("section") or "",
                    "enrollment_code": meta.get("enrollment_code") or "",
                    "label": _course_label(meta),
                }
            )
        profile = profiles.get(sid) or {}
        out.append(
            {
                "student_id": sid,
                "student_name": name,
                "display_name": profile.get("display_name", ""),
                "email": profile.get("email", ""),
                "mobile": profile.get("mobile", ""),
                "updated_at": profile.get("updated_at", ""),
                "in_roster": True,
                "courses": course_chips,
            }
        )
    for sid, profile in profiles.items():
        if sid in seen:
            continue
        out.append(
            {
                "student_id": sid,
                "student_name": profile.get("display_name") or sid,
                "display_name": profile.get("display_name", ""),
                "email": profile.get("email", ""),
                "mobile": profile.get("mobile", ""),
                "updated_at": profile.get("updated_at", ""),
                "in_roster": False,
                "courses": [],
            }
        )
    out.sort(key=lambda r: ((r.get("display_name") or r.get("student_name") or "").lower()))
    return out


def upsert_student_profile(
    drive,
    reports_folder_id: str,
    student_id: str,
    *,
    display_name: str | None = None,
    email: str | None = None,
    mobile: str | None = None,
) -> dict:
    from tools.student_profiles import save_profile

    row = save_profile(
        drive,
        reports_folder_id,
        student_id,
        display_name=display_name,
        email=email,
        mobile=mobile,
    )
    invalidate_queue_cache()
    return {
        "student_id": row["student_id"],
        "student_name": row.get("display_name") or row["student_id"],
        "display_name": row.get("display_name", ""),
        "email": row.get("email", ""),
        "mobile": row.get("mobile", ""),
        "updated_at": row.get("updated_at", ""),
        "in_roster": False,
        "courses": [],
    }


# ═════════════════════════ scores matrix + reports list ═════════════════════════

def score_matrix(
    classroom,
    drive,
    keys_folder_id: str,
    reports_folder_id: str,
    course_ids: list[str],
    classroom_factory: Callable[[], Any] | None = None,
) -> dict:
    from tools.student_profiles import load_profiles

    rows = _read_scores_csv(drive, reports_folder_id)
    profiles = load_profiles(drive, reports_folder_id)

    assignments: dict[tuple[str, str], dict] = {}
    cells: dict[str, dict[str, dict]] = {}
    students: dict[str, dict] = {}

    for r in rows:
        try:
            atype = r.get("assignment_type") or ""
            acode = r.get("assignment_code") or ""
            if not (atype and acode):
                continue
            key = f"{atype}_{acode}"
            try:
                pct = float(r.get("percentage") or 0.0)
            except (TypeError, ValueError):
                continue
            earned = float(r.get("graded_earned") or 0.0)
            max_score = float(r.get("graded_max") or 0.0)
            edate = r.get("evaluation_date") or ""
            atup = (atype, acode)
            if atup not in assignments or (
                edate > (assignments[atup].get("evaluation_date") or "")
            ):
                assignments[atup] = {
                    "key": key,
                    "assignment_type": atype,
                    "assignment_code": acode,
                    "assignment_title": r.get("assignment_title") or "",
                    "evaluation_date": edate,
                    "max_score": max_score,
                    "coursework_id": r.get("coursework_id"),
                }
            sid = r.get("student_id") or ""
            if sid:
                cells.setdefault(sid, {})[key] = {
                    "earned": round(earned, 2),
                    "max": round(max_score, 2),
                    "percentage": round(pct, 2),
                }
                students.setdefault(
                    sid,
                    {
                        "student_id": sid,
                        "student_name": r.get("student_name") or "",
                        "display_name": (profiles.get(sid) or {}).get("display_name", ""),
                        "courses": [],
                    },
                )
        except Exception as exc:  # noqa: BLE001
            log.exception("score_matrix row failed: %s", exc)
            continue

    courses_out: list[dict] = []
    if course_ids:
        # Per-course metadata + rosters. Parallel fan-out when a thread-safe
        # client factory is supplied; otherwise serial (matches
        # list_students_with_profiles). Per-course failures are tolerated.
        course_metas: dict[str, dict] = {}
        rosters: dict[str, dict[str, str]] = {}
        if classroom_factory is None:
            for cid in course_ids:
                try:
                    course_metas[cid] = _course_meta(classroom, cid)
                except Exception as exc:  # noqa: BLE001
                    log.warning("score_matrix meta failed for %s: %s", cid, exc)
                    continue
                try:
                    rosters[cid] = _roster(classroom, cid)
                except Exception as exc:  # noqa: BLE001
                    log.warning("score_matrix roster failed for %s: %s", cid, exc)
        else:
            tls = threading.local()

            def _client():
                existing = getattr(tls, "c", None)
                if existing is None:
                    existing = classroom_factory()
                    tls.c = existing
                return existing

            def _safe_meta(c: str):
                try:
                    return _course_meta(_client(), c)
                except Exception as exc:  # noqa: BLE001
                    log.warning("score_matrix meta failed for %s: %s", c, exc)
                    return None

            def _safe_roster(c: str):
                try:
                    return _roster(_client(), c)
                except Exception as exc:  # noqa: BLE001
                    log.warning("score_matrix roster failed for %s: %s", c, exc)
                    return {}

            with ThreadPoolExecutor(max_workers=min(len(course_ids), 4)) as ex:
                for cid, meta in zip(course_ids, ex.map(_safe_meta, course_ids)):
                    if meta is not None:
                        course_metas[cid] = meta
                for cid, roster in zip(course_ids, ex.map(_safe_roster, course_ids)):
                    rosters[cid] = roster

        for cid in course_ids:
            meta = course_metas.get(cid)
            if meta is None:
                continue
            courses_out.append(
                {
                    "course_id": cid,
                    "label": _course_label(meta),
                    "section": meta.get("section"),
                    "enrollment_code": meta.get("enrollment_code"),
                }
            )
            for sid in rosters.get(cid, {}):
                if sid in students:
                    students[sid].setdefault("courses", []).append(
                        {
                            "course_id": cid,
                            "name": meta.get("name", ""),
                            "section": meta.get("section", ""),
                            "enrollment_code": meta.get("enrollment_code", ""),
                            "label": _course_label(meta),
                        }
                    )

    assignments_list = sorted(
        assignments.values(),
        key=lambda a: (a["assignment_type"], a["assignment_code"]),
    )
    students_list = sorted(
        students.values(),
        key=lambda s: (s.get("display_name") or s.get("student_name") or "").lower(),
    )
    return {
        "assignments": assignments_list,
        "students": students_list,
        "cells": cells,
        "courses": courses_out,
    }


def list_all_reports(
    classroom,
    drive,
    keys_folder_id: str,
    reports_folder_id: str,
    course_ids: list[str],
) -> list[dict]:
    rows = _read_scores_csv(drive, reports_folder_id)
    queue = list_queue(classroom, drive, keys_folder_id, course_ids)
    title_by_code = {
        (q["assignment_type"], q["assignment_code"]): q.get("assignment_title", "")
        for q in queue
    }
    index = _index_reports(drive, reports_folder_id)
    out: list[dict] = []
    for r in rows:
        try:
            atype = r.get("assignment_type") or ""
            acode = r.get("assignment_code") or ""
            pct = float(r.get("percentage") or 0.0)
            edate = r.get("evaluation_date") or ""
            drive_id, view_url = _match_report(index, r)
            out.append(
                {
                    "student_id": r.get("student_id") or "",
                    "student_name": r.get("student_name") or "",
                    "assignment_type": atype or "WA",
                    "assignment_code": acode,
                    "assignment_title": (
                        r.get("assignment_title")
                        or title_by_code.get((atype, acode), "")
                    ),
                    "coursework_id": r.get("coursework_id"),
                    "percentage": round(pct, 1),
                    "band": _band_for(pct),
                    "evaluation_date": edate,
                    "report_drive_id": drive_id or "",
                    "report_url": view_url or "",
                    "linked_at": r.get("linked_at"),
                    "unlinked_at": r.get("unlinked_at"),
                    "shared_with_email": r.get("shared_with_email"),
                    "drive_permission_id": r.get("drive_permission_id"),
                    "eval_duration_seconds": r.get("eval_duration_seconds"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("list_all_reports row failed: %s", exc)
            continue
    out.sort(key=lambda r: r.get("evaluation_date") or "", reverse=True)
    return out
