"""
Append a student's evaluation result to scores.csv stored in the Drive reports/ folder.
Creates scores.csv if it doesn't exist.

Usage:
    python tools/track_scores.py '<evaluation_json>'
"""

import csv
import io
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")

SCORES_FILENAME = "scores.csv"
CSV_HEADER = [
    "assignment_type", "assignment_code", "student_id", "student_name",
    "evaluation_date", "total_questions", "earned_score", "max_score",
    "percentage",
    "concept_pct", "approach_pct", "steps_pct", "accuracy_pct", "clarity_pct",
    "qualifies_for",
]


def get_creds():
    token_path = os.path.join(os.path.dirname(__file__), "..", "token.json")
    from tools.setup_drive import SCOPES
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def _dim_avg(questions: list, dim_key: str) -> float:
    scores = [q["dimensions"][dim_key]["score"] for q in questions]
    return round(sum(scores) / len(scores) * 100, 1) if scores else 0.0


def build_row(ev: dict) -> dict:
    s = ev["summary"]
    qs = ev["questions"]
    return {
        "assignment_type": ev["assignment"]["type"],
        "assignment_code": ev["assignment"]["code"],
        "student_id": ev["student"]["id"],
        "student_name": ev["student"]["name"],
        "evaluation_date": ev.get("evaluation_date", date.today().isoformat()),
        "total_questions": s["total_questions"],
        "earned_score": s["earned_score"],
        "max_score": s["max_score"],
        "percentage": s["percentage"],
        "concept_pct": _dim_avg(qs, "concept_understanding"),
        "approach_pct": _dim_avg(qs, "approach_method"),
        "steps_pct": _dim_avg(qs, "step_by_step"),
        "accuracy_pct": _dim_avg(qs, "numerical_accuracy"),
        "clarity_pct": _dim_avg(qs, "presentation"),
        "qualifies_for": s.get("qualifies_for") or "",
    }


def load_csv(drive, folder_id: str) -> tuple[str | None, list[dict]]:
    """Returns (file_id_or_None, list_of_row_dicts)."""
    query = f"name='{SCORES_FILENAME}' and '{folder_id}' in parents and trashed=false"
    results = drive.files().list(q=query, fields="files(id)").execute()
    files = results.get("files", [])
    if not files:
        return None, []

    file_id = files[0]["id"]
    request = drive.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    content = buf.getvalue().decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    return file_id, list(reader)


def save_csv(drive, folder_id: str, file_id: str | None, rows: list[dict]):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_HEADER)
    writer.writeheader()
    writer.writerows(rows)
    content = buf.getvalue().encode("utf-8")

    media = MediaIoBaseUpload(io.BytesIO(content), mimetype="text/csv", resumable=False)

    if file_id:
        drive.files().update(fileId=file_id, media_body=media).execute()
    else:
        metadata = {"name": SCORES_FILENAME, "parents": [folder_id]}
        drive.files().create(body=metadata, media_body=media, fields="id").execute()


def track(evaluation: dict, reports_folder_id: str):
    creds = get_creds()
    drive = build("drive", "v3", credentials=creds)

    file_id, rows = load_csv(drive, reports_folder_id)

    new_row = build_row(evaluation)

    # Replace existing entry for same student+assignment if present
    key = (new_row["assignment_type"], new_row["assignment_code"], new_row["student_id"])
    rows = [r for r in rows if (r.get("assignment_type"), r.get("assignment_code"), r.get("student_id")) != key]
    rows.append(new_row)

    save_csv(drive, reports_folder_id, file_id, rows)
    print(f"scores.csv updated — {new_row['student_name']} "
          f"{new_row['assignment_type']} {new_row['assignment_code']}: "
          f"{new_row['percentage']}%", file=sys.stderr)


def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/track_scores.py '<evaluation_json>'", file=sys.stderr)
        sys.exit(1)

    load_dotenv(ENV_PATH)
    evaluation = json.loads(sys.argv[1])
    reports_id = os.getenv("DRIVE_REPORTS_ID", "").strip()
    if not reports_id:
        print("DRIVE_REPORTS_ID not set.", file=sys.stderr)
        sys.exit(1)

    track(evaluation, reports_id)


if __name__ == "__main__":
    main()
