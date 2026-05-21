"""
Persist + read editable student profile fields (display name, email,
mobile). Identity comes from the live Google Classroom roster — these
fields live in Postgres for fast lookup and are mirrored to a
``students.csv`` on Drive for human-readable export.

Schema (Postgres ``student_profiles`` table — created by an external
migration):

    student_id      text primary key
    display_name    text
    email           text
    mobile          text
    updated_at      timestamptz
"""
from __future__ import annotations

import csv
import io
import threading
from datetime import datetime, timezone
from typing import Any

from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from tools import db

STUDENTS_FILENAME = "students.csv"
CSV_HEADER = ["student_id", "display_name", "email", "mobile", "updated_at"]

_PROFILE_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_file(drive, folder_id: str) -> str | None:
    resp = (
        drive.files()
        .list(
            q=f"name='{STUDENTS_FILENAME}' and '{folder_id}' in parents and trashed=false",
            spaces="drive",
            fields="files(id, name)",
            pageSize=1,
        )
        .execute()
    )
    files = resp.get("files", [])
    return files[0]["id"] if files else None


def _read(drive, folder_id: str) -> tuple[str | None, list[dict[str, str]]]:
    file_id = _find_file(drive, folder_id)
    if not file_id:
        return None, []
    req = drive.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    rows = list(csv.DictReader(io.StringIO(buf.getvalue().decode("utf-8"))))
    return file_id, rows


def _write(drive, folder_id: str, file_id: str | None, rows: list[dict[str, str]]) -> str:
    rows = sorted(rows, key=lambda r: (r.get("student_id") or "").lower())
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_HEADER)
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k, "") for k in CSV_HEADER})
    media = MediaIoBaseUpload(
        io.BytesIO(out.getvalue().encode("utf-8")),
        mimetype="text/csv",
        resumable=False,
    )
    if file_id:
        drive.files().update(fileId=file_id, media_body=media).execute()
        return file_id
    created = (
        drive.files()
        .create(
            body={
                "name": STUDENTS_FILENAME,
                "parents": [folder_id],
                "mimeType": "text/csv",
            },
            media_body=media,
            fields="id",
        )
        .execute()
    )
    return created["id"]


def load_profiles(drive, reports_folder_id: str) -> dict[str, dict[str, Any]]:
    """Return ``{student_id: profile_dict}`` from Postgres if the table
    exists, otherwise from the Drive CSV mirror.

    ``reports_folder_id`` is accepted for backward compatibility with the
    older Drive-only path. Postgres is the preferred truth, but a missing
    table (e.g. fresh setup, no migration run) is not fatal — we fall
    through to the CSV.
    """
    try:
        rows = db.fetch_all(
            "SELECT student_id, display_name, email, mobile, updated_at "
            "FROM student_profiles"
        )
    except Exception:
        # No table, no DB connection, or any other read failure → fall
        # back to the Drive CSV mirror so callers still get something.
        try:
            if drive and reports_folder_id:
                _, csv_rows = _read(drive, reports_folder_id)
            else:
                csv_rows = []
        except Exception:
            csv_rows = []
        out: dict[str, dict[str, Any]] = {}
        for r in csv_rows:
            sid = (r.get("student_id") or "").strip()
            if not sid:
                continue
            out[sid] = {
                "student_id": sid,
                "display_name": r.get("display_name") or "",
                "email": r.get("email") or "",
                "mobile": r.get("mobile") or "",
                "updated_at": r.get("updated_at") or "",
            }
        return out
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        sid = (r.get("student_id") or "").strip()
        if not sid:
            continue
        updated = r.get("updated_at")
        out[sid] = {
            "student_id": sid,
            "display_name": r.get("display_name") or "",
            "email": r.get("email") or "",
            "mobile": r.get("mobile") or "",
            "updated_at": (
                updated.isoformat() if hasattr(updated, "isoformat") else (updated or "")
            ),
        }
    return out


def lookup_email(drive, reports_folder_id: str, student_id: str) -> str:
    profile = load_profiles(drive, reports_folder_id).get(student_id) or {}
    return (profile.get("email") or "").strip()


def save_profile(
    drive,
    reports_folder_id: str,
    student_id: str,
    *,
    display_name: str | None = None,
    email: str | None = None,
    mobile: str | None = None,
) -> dict[str, Any]:
    sid = (student_id or "").strip()
    if not sid:
        raise ValueError("student_id required")
    now = _now_iso()
    db.execute(
        """
        INSERT INTO student_profiles (student_id, display_name, email, mobile, updated_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (student_id) DO UPDATE
        SET display_name = COALESCE(EXCLUDED.display_name, student_profiles.display_name),
            email        = COALESCE(EXCLUDED.email,        student_profiles.email),
            mobile       = COALESCE(EXCLUDED.mobile,       student_profiles.mobile),
            updated_at   = EXCLUDED.updated_at
        """,
        (sid, display_name, email, mobile, now),
    )
    row = db.fetch_one(
        "SELECT student_id, display_name, email, mobile, updated_at "
        "FROM student_profiles WHERE student_id = %s",
        (sid,),
    ) or {}
    updated = row.get("updated_at")
    return {
        "student_id": sid,
        "display_name": row.get("display_name") or "",
        "email": row.get("email") or "",
        "mobile": row.get("mobile") or "",
        "updated_at": (
            updated.isoformat() if hasattr(updated, "isoformat") else (updated or "")
        ),
    }


def save_profile_many(
    drive,
    reports_folder_id: str,
    items: list[dict[str, Any]],
) -> None:
    if not items:
        return
    now = _now_iso()
    rows = []
    for it in items:
        sid = (it.get("student_id") or "").strip()
        if not sid:
            continue
        rows.append(
            (
                sid,
                it.get("display_name"),
                it.get("email"),
                it.get("mobile"),
                now,
            )
        )
    if not rows:
        return
    db.execute_many(
        """
        INSERT INTO student_profiles (student_id, display_name, email, mobile, updated_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (student_id) DO UPDATE
        SET display_name = COALESCE(EXCLUDED.display_name, student_profiles.display_name),
            email        = COALESCE(EXCLUDED.email,        student_profiles.email),
            mobile       = COALESCE(EXCLUDED.mobile,       student_profiles.mobile),
            updated_at   = EXCLUDED.updated_at
        """,
        rows,
    )
