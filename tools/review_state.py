"""
Drive-stored state tracking for the answer-key review workflow.

State is a single JSON file 'answer_key_state.json' in the answer_keys/ folder:
{
  "<coursework_id>": {
    "course_id": "...",
    "coursework_id": "...",
    "assignment_type": "WA",
    "assignment_code": "DOM2",
    "assignment_title": "...",
    "status": "PENDING_REVIEW",   # GENERATING | PENDING_REVIEW | NEEDS_REGEN | APPROVED
    "current_otp": "AB12CD",
    "thread_id": "<gmail thread>",
    "regen_count": 0,
    "questions_status": ["approved", "needs_rework", ...],   # per Q index
    "approved_at": null,
    "drive_pdf_id": "..."
  }
}
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

STATE_FILENAME = "answer_key_state.json"


def _find_state_file(drive, folder_id: str):
    query = f"name='{STATE_FILENAME}' and '{folder_id}' in parents and trashed=false"
    files = drive.files().list(q=query, fields="files(id)").execute().get("files", [])
    return files[0]["id"] if files else None


def load_state(drive, folder_id: str) -> dict:
    file_id = _find_state_file(drive, folder_id)
    if not file_id:
        return {}
    request = drive.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    try:
        return json.loads(buf.getvalue().decode("utf-8"))
    except json.JSONDecodeError:
        return {}


def save_state(drive, folder_id: str, state: dict):
    content = json.dumps(state, indent=2, sort_keys=True).encode("utf-8")
    media = MediaIoBaseUpload(
        io.BytesIO(content), mimetype="application/json", resumable=False
    )
    file_id = _find_state_file(drive, folder_id)
    if file_id:
        drive.files().update(fileId=file_id, media_body=media).execute()
    else:
        metadata = {"name": STATE_FILENAME, "parents": [folder_id]}
        drive.files().create(body=metadata, media_body=media, fields="id").execute()


def is_approved(state: dict, coursework_id: str) -> bool:
    entry = state.get(coursework_id)
    return bool(entry) and entry.get("status") == "APPROVED"
